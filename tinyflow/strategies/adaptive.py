"""
Adaptive Packet Aggregation Strategy.
Dynamically decides whether to transmit or continue buffering based on:
- Buffer occupancy relative to MTU limit
- Network queue congestion and estimated delay
- Reading urgency / priority
- Oldest reading age and maximum waiting time
- Delivery deadlines and safety slack margins
"""

from __future__ import annotations
from typing import Any, List, Optional
from tinyflow.models import (
    DecisionAction,
    DecisionReasonCode,
    DecisionRecord,
    Packet,
    ReadingPriority,
    SensorReading,
)
from tinyflow.strategies.base import BaseAggregationStrategy


class AdaptiveAggregationStrategy(BaseAggregationStrategy):
    """
    Adaptive Aggregation Strategy:
    Evaluates real-time network and buffer conditions using documented multi-variable rules.
    Balances packet-header reduction against delivery latency and deadline guarantees.
    """

    def __init__(
        self,
        max_wait_time_s: float = 0.8,
        safety_slack_margin_s: float = 0.25,
        congestion_queue_threshold: int = 4,
        urgent_flush_high: bool = True,
        header_bytes: int = 28,
        framing_bytes_per_reading: int = 2,
        max_packet_size: int = 128,
    ):
        super().__init__(
            name="Adaptive",
            header_bytes=header_bytes,
            framing_bytes_per_reading=framing_bytes_per_reading,
            max_packet_size=max_packet_size,
        )
        self.max_wait_time_s = max(0.1, max_wait_time_s)
        self.safety_slack_margin_s = max(0.05, safety_slack_margin_s)
        self.congestion_queue_threshold = max(1, congestion_queue_threshold)
        self.urgent_flush_high = urgent_flush_high

    def _evaluate_state(
        self, current_time: float, network_state: Any, incoming_reading: Optional[SensorReading] = None
    ) -> tuple[DecisionAction, DecisionReasonCode, str]:
        """
        Evaluates the dynamic decision policy against current internal state.
        Returns (action, reason_code, explanation_text).
        """
        combined = list(self.buffer)
        if incoming_reading:
            combined.append(incoming_reading)

        if not combined:
            return (
                DecisionAction.WAIT,
                DecisionReasonCode.EMPTY_BUFFER,
                "Buffer is empty; awaiting sensor readings.",
            )

        # 1. Inspect reading urgencies
        has_critical = any(r.priority == ReadingPriority.CRITICAL for r in combined)
        has_high = any(r.priority == ReadingPriority.HIGH for r in combined)
        if has_critical or (self.urgent_flush_high and has_high):
            top_priority = "CRITICAL" if has_critical else "HIGH"
            return (
                DecisionAction.TRANSMIT,
                DecisionReasonCode.URGENT_PRIORITY_TRIGGER,
                f"Urgent priority reading received (priority={top_priority}). Immediate transmission triggered to minimize latency.",
            )

        # 2. Inspect buffer capacity vs MTU limit
        total_reading_payload = sum(r.payload_bytes for r in combined)
        total_framing = len(combined) * self.framing_bytes_per_reading
        projected_pkt_size = self.header_bytes + total_reading_payload + total_framing
        
        # Check if buffer is at or near MTU capacity (cannot fit another standard reading)
        nominal_reading_wire_cost = 14 + self.framing_bytes_per_reading
        if projected_pkt_size + nominal_reading_wire_cost > self.max_packet_size:
            return (
                DecisionAction.TRANSMIT,
                DecisionReasonCode.BUFFER_FULL_MTU,
                f"Buffer occupancy ({projected_pkt_size}B) approaching MTU limit ({self.max_packet_size}B, {len(combined)} readings). Transmitting full batch.",
            )

        # 3. Inspect deadlines and delivery slack
        queue_len = getattr(network_state, "queue_len", 0)
        est_queue_delay = getattr(network_state, "est_queue_delay", 0.0)
        channel_tx_time = getattr(network_state, "est_tx_time_per_packet", 0.01)
        est_network_delay = est_queue_delay + channel_tx_time

        min_slack = min(r.slack(current_time) for r in combined)
        effective_min_slack = min_slack - est_network_delay

        if effective_min_slack <= self.safety_slack_margin_s:
            oldest_age = current_time - combined[0].timestamp
            return (
                DecisionAction.TRANSMIT,
                DecisionReasonCode.DEADLINE_APPROACHING,
                f"Deadline approaching safe margin (min slack={min_slack:.3f}s, est network delay={est_network_delay:.3f}s, safety margin={self.safety_slack_margin_s:.3f}s, oldest age={oldest_age:.3f}s).",
            )

        # 4. Inspect oldest reading wait time
        oldest_age = current_time - combined[0].timestamp
        # Congestion adaptively tightens max wait time if channel is congested
        dynamic_max_wait = self.max_wait_time_s
        if queue_len >= self.congestion_queue_threshold:
            # Reduce allowable wait time proportionally to queue backlog
            dynamic_max_wait = max(0.1, self.max_wait_time_s * 0.6)

        if oldest_age >= dynamic_max_wait:
            return (
                DecisionAction.TRANSMIT,
                DecisionReasonCode.MAX_WAIT_EXCEEDED,
                f"Oldest reading age ({oldest_age:.3f}s) exceeded dynamic max wait threshold ({dynamic_max_wait:.3f}s under queue={queue_len}). Flushing batch.",
            )

        # 5. Inspect network backlog / congestion flush
        if queue_len >= self.congestion_queue_threshold and len(combined) >= 3:
            return (
                DecisionAction.TRANSMIT,
                DecisionReasonCode.CONGESTION_FLUSH,
                f"Network congestion detected ({queue_len} packets in queue, est delay={est_queue_delay:.3f}s). Flushing {len(combined)} aggregated readings to avoid head-of-line queue delay.",
            )

        # 6. Default action: Safe to aggregate
        return (
            DecisionAction.WAIT,
            DecisionReasonCode.BUFFER_ROOM_WAITING,
            f"Buffer has space ({projected_pkt_size}B/{self.max_packet_size}B) and safe slack ({min_slack:.3f}s > {self.safety_slack_margin_s:.3f}s). Holding {len(combined)} readings for aggregation efficiency.",
        )

    def on_reading_arrived(
        self, reading: SensorReading, current_time: float, network_state: Any
    ) -> List[Packet]:
        action, reason_code, reason_text = self._evaluate_state(
            current_time, network_state, incoming_reading=reading
        )

        oldest_age = (
            current_time - (self.buffer[0].timestamp if self.buffer else reading.timestamp)
        )
        min_slack = min(
            r.slack(current_time)
            for r in (self.buffer + [reading])
        )

        if action == DecisionAction.TRANSMIT:
            # Add reading to buffer, then flush as MTU packets
            self.buffer.append(reading)
            pkts = self._pack_readings_into_packets(self.buffer, current_time)
            flushed_count = len(self.buffer)
            self.buffer.clear()

            for pkt in pkts:
                rec = DecisionRecord(
                    timestamp=current_time,
                    action=action,
                    reason_code=reason_code,
                    reason_text=reason_text,
                    buffer_count=flushed_count,
                    buffer_bytes=pkt.payload_bytes,
                    oldest_reading_age=oldest_age,
                    min_slack=min_slack,
                    queue_occupancy=getattr(network_state, "queue_len", 0),
                    estimated_queue_delay=getattr(network_state, "est_queue_delay", 0.0),
                    packet_id=pkt.id,
                    readings_count=len(pkt.readings),
                )
                self.decisions.append(rec)
            return pkts
        else:
            # Buffer the reading and record the WAIT decision
            self.buffer.append(reading)
            rec = DecisionRecord(
                timestamp=current_time,
                action=action,
                reason_code=reason_code,
                reason_text=reason_text,
                buffer_count=len(self.buffer),
                buffer_bytes=self.buffer_bytes,
                oldest_reading_age=oldest_age,
                min_slack=min_slack,
                queue_occupancy=getattr(network_state, "queue_len", 0),
                estimated_queue_delay=getattr(network_state, "est_queue_delay", 0.0),
                packet_id=None,
                readings_count=len(self.buffer),
            )
            self.decisions.append(rec)
            return []

    def on_timer_tick(
        self, current_time: float, network_state: Any
    ) -> List[Packet]:
        """Periodic check for deadline/max wait conditions on buffered items."""
        if not self.buffer:
            return []

        action, reason_code, reason_text = self._evaluate_state(
            current_time, network_state, incoming_reading=None
        )

        oldest_age = current_time - self.buffer[0].timestamp
        min_slack = min(r.slack(current_time) for r in self.buffer)

        if action == DecisionAction.TRANSMIT:
            pkts = self._pack_readings_into_packets(self.buffer, current_time)
            flushed_count = len(self.buffer)
            self.buffer.clear()

            for pkt in pkts:
                rec = DecisionRecord(
                    timestamp=current_time,
                    action=action,
                    reason_code=reason_code,
                    reason_text=reason_text,
                    buffer_count=flushed_count,
                    buffer_bytes=pkt.payload_bytes,
                    oldest_reading_age=oldest_age,
                    min_slack=min_slack,
                    queue_occupancy=getattr(network_state, "queue_len", 0),
                    estimated_queue_delay=getattr(network_state, "est_queue_delay", 0.0),
                    packet_id=pkt.id,
                    readings_count=len(pkt.readings),
                )
                self.decisions.append(rec)
            return pkts

        return []

    def flush_residual(self, current_time: float) -> List[Packet]:
        if not self.buffer:
            return []
        pkts = self._pack_readings_into_packets(self.buffer, current_time)
        flushed_count = len(self.buffer)
        oldest_age = current_time - self.buffer[0].timestamp
        min_slack = min(r.slack(current_time) for r in self.buffer)
        self.buffer.clear()

        for pkt in pkts:
            rec = DecisionRecord(
                timestamp=current_time,
                action=DecisionAction.TRANSMIT,
                reason_code=DecisionReasonCode.SIMULATION_TERMINATION,
                reason_text=f"Simulation duration reached. Flushed residual batch of {len(pkt.readings)} readings.",
                buffer_count=flushed_count,
                buffer_bytes=pkt.payload_bytes,
                oldest_reading_age=oldest_age,
                min_slack=min_slack,
                queue_occupancy=0,
                estimated_queue_delay=0.0,
                packet_id=pkt.id,
                readings_count=len(pkt.readings),
            )
            self.decisions.append(rec)
        return pkts
