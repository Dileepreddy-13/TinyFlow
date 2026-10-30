"""
Base class and common interfaces for aggregation strategies.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, List, Optional
from tinyflow.models import DecisionRecord, Packet, SensorReading


class BaseAggregationStrategy(ABC):
    """
    Abstract base class for IoT packet aggregation policies.
    """

    def __init__(
        self,
        name: str,
        header_bytes: int = 28,
        framing_bytes_per_reading: int = 2,
        max_packet_size: int = 128,
    ):
        self.name = name
        self.header_bytes = header_bytes
        self.framing_bytes_per_reading = framing_bytes_per_reading
        self.max_packet_size = max_packet_size
        self.buffer: List[SensorReading] = []
        self.decisions: List[DecisionRecord] = []
        self._seq_counter = 0

    @property
    def buffer_count(self) -> int:
        return len(self.buffer)

    @property
    def buffer_bytes(self) -> int:
        if not self.buffer:
            return 0
        raw = sum(r.payload_bytes for r in self.buffer)
        framing = len(self.buffer) * self.framing_bytes_per_reading
        return raw + framing

    def _next_seq(self) -> int:
        self._seq_counter += 1
        return self._seq_counter

    def _create_packet(
        self, readings: List[SensorReading], creation_time: float
    ) -> Packet:
        """Helper to assemble a packet from a list of readings."""
        seq = self._next_seq()
        pkt_id = f"pkt_{self.name[:3]}_{seq}_{creation_time:.3f}"
        return Packet(
            id=pkt_id,
            sequence_number=seq,
            creation_time=creation_time,
            readings=readings,
            header_bytes=self.header_bytes,
            framing_bytes_per_reading=self.framing_bytes_per_reading,
            max_packet_size=self.max_packet_size,
            strategy_name=self.name,
        )

    def _pack_readings_into_packets(
        self, readings: List[SensorReading], creation_time: float
    ) -> List[Packet]:
        """
        Packs a list of readings into one or more packets respecting MTU.
        """
        if not readings:
            return []

        packets: List[Packet] = []
        current_batch: List[SensorReading] = []
        current_payload = 0

        for r in readings:
            needed = r.payload_bytes + self.framing_bytes_per_reading
            if current_batch and (self.header_bytes + current_payload + needed > self.max_packet_size):
                # Packet full, ship it
                packets.append(self._create_packet(current_batch, creation_time))
                current_batch = [r]
                current_payload = needed
            else:
                current_batch.append(r)
                current_payload += needed

        if current_batch:
            packets.append(self._create_packet(current_batch, creation_time))

        return packets

    @abstractmethod
    def on_reading_arrived(
        self, reading: SensorReading, current_time: float, network_state: Any
    ) -> List[Packet]:
        """Called when a new sensor reading is generated."""
        pass

    @abstractmethod
    def on_timer_tick(
        self, current_time: float, network_state: Any
    ) -> List[Packet]:
        """Called periodically or when a scheduled strategy timer fires."""
        pass

    @abstractmethod
    def flush_residual(self, current_time: float) -> List[Packet]:
        """Flushes any remaining readings when the simulation reaches its end."""
        pass
