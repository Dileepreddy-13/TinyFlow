"""
Fixed-Interval Batching Strategy.
Buffers readings and transmits accumulated batches at a configurable periodic interval,
or when the buffer reaches MTU capacity limit.
"""

from __future__ import annotations
from typing import Any, List
from tinyflow.models import (
    DecisionAction,
    DecisionReasonCode,
    DecisionRecord,
    Packet,
    SensorReading,
)
from tinyflow.strategies.base import BaseAggregationStrategy


class FixedIntervalBatchingStrategy(BaseAggregationStrategy):
    """
    Fixed-Interval Batching Strategy:
    Accumulates readings in a FIFO buffer. Transmits when the fixed timer expires
    (e.g., every 1.0s) or immediately if the buffer reaches MTU capacity.
    """

    def __init__(
        self,
        batch_interval_s: float = 1.0,
        header_bytes: int = 28,
        framing_bytes_per_reading: int = 2,
        max_packet_size: int = 128,
    ):
        super().__init__(
            name="Fixed-Interval",
            header_bytes=header_bytes,
            framing_bytes_per_reading=framing_bytes_per_reading,
            max_packet_size=max_packet_size,
        )
        self.batch_interval_s = max(0.05, batch_interval_s)
        self.last_flush_time = 0.0

    def on_reading_arrived(
        self, reading: SensorReading, current_time: float, network_state: Any
    ) -> List[Packet]:
        # Check if adding this reading would exceed MTU limit for a single packet
        needed_bytes = reading.payload_bytes + self.framing_bytes_per_reading
        current_projected = self.header_bytes + self.buffer_bytes + needed_bytes

        if self.buffer and current_projected > self.max_packet_size:
            # Buffer full trigger
            pkts = self._pack_readings_into_packets(self.buffer, current_time)
            flushed_count = len(self.buffer)
            self.buffer = [reading]
            self.last_flush_time = current_time

            for pkt in pkts:
                rec = DecisionRecord(
                    timestamp=current_time,
                    action=DecisionAction.TRANSMIT,
                    reason_code=DecisionReasonCode.BUFFER_FULL_MTU,
                    reason_text=(
                        f"Fixed batch buffer reached MTU ({current_projected}B > {self.max_packet_size}B). "
                        f"Flushed batch of {flushed_count} readings."
                    ),
                    buffer_count=flushed_count,
                    buffer_bytes=pkt.payload_bytes,
                    oldest_reading_age=current_time - pkt.readings[0].timestamp if pkt.readings else 0.0,
                    min_slack=min(r.slack(current_time) for r in pkt.readings) if pkt.readings else 0.0,
                    queue_occupancy=getattr(network_state, "queue_len", 0),
                    estimated_queue_delay=getattr(network_state, "est_queue_delay", 0.0),
                    packet_id=pkt.id,
                    readings_count=len(pkt.readings),
                )
                self.decisions.append(rec)
            return pkts

        # Otherwise simply buffer
        self.buffer.append(reading)
        return []

    def on_timer_tick(
        self, current_time: float, network_state: Any
    ) -> List[Packet]:
        """Called when the periodic batch interval timer fires."""
        if not self.buffer:
            return []

        pkts = self._pack_readings_into_packets(self.buffer, current_time)
        flushed_count = len(self.buffer)
        oldest_age = current_time - self.buffer[0].timestamp
        min_slack = min(r.slack(current_time) for r in self.buffer)
        self.buffer.clear()
        self.last_flush_time = current_time

        for pkt in pkts:
            rec = DecisionRecord(
                timestamp=current_time,
                action=DecisionAction.TRANSMIT,
                reason_code=DecisionReasonCode.MAX_WAIT_EXCEEDED,
                reason_text=(
                    f"Fixed timer interval ({self.batch_interval_s:.2f}s) expired. "
                    f"Transmitted batch of {len(pkt.readings)} readings (oldest age: {oldest_age:.3f}s)."
                ),
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

    def flush_residual(self, current_time: float) -> List[Packet]:
        if not self.buffer:
            return []
        pkts = self._pack_readings_into_packets(self.buffer, current_time)
        self.buffer.clear()
        return pkts
