"""
Immediate Transmission Strategy.
Transmits every sensor reading as an individual packet as soon as it arrives.
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


class ImmediateStrategy(BaseAggregationStrategy):
    """
    Immediate Transmission Strategy:
    Zero waiting time; encapsulates each reading into its own standalone packet.
    Exhibits minimal buffering delay but maximum packet-header overhead.
    """

    def __init__(
        self,
        header_bytes: int = 28,
        framing_bytes_per_reading: int = 2,
        max_packet_size: int = 128,
    ):
        super().__init__(
            name="Immediate",
            header_bytes=header_bytes,
            framing_bytes_per_reading=framing_bytes_per_reading,
            max_packet_size=max_packet_size,
        )

    def on_reading_arrived(
        self, reading: SensorReading, current_time: float, network_state: Any
    ) -> List[Packet]:
        pkt = self._create_packet([reading], current_time)
        
        # Record decision for transparency
        record = DecisionRecord(
            timestamp=current_time,
            action=DecisionAction.TRANSMIT,
            reason_code=DecisionReasonCode.URGENT_PRIORITY_TRIGGER,
            reason_text=f"Immediate transmission policy: reading {reading.id} (priority={reading.priority.name}) transmitted immediately upon arrival.",
            buffer_count=0,
            buffer_bytes=0,
            oldest_reading_age=0.0,
            min_slack=reading.slack(current_time),
            queue_occupancy=getattr(network_state, "queue_len", 0),
            estimated_queue_delay=getattr(network_state, "est_queue_delay", 0.0),
            packet_id=pkt.id,
            readings_count=1,
        )
        self.decisions.append(record)
        return [pkt]

    def on_timer_tick(
        self, current_time: float, network_state: Any
    ) -> List[Packet]:
        # Immediate strategy does not use timers since nothing is ever buffered
        return []

    def flush_residual(self, current_time: float) -> List[Packet]:
        return []
