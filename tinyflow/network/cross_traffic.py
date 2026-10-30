"""
Cross-traffic and network congestion generator.
Provides realistic competing background traffic to model link contention and queue buildup.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import numpy as np

from tinyflow.models import Packet


class CongestionPreset(str, Enum):
    """Documented congestion presets mapped to concrete background traffic rates."""
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"

    @property
    def packet_rate_hz(self) -> float:
        """Arrival rate (packets/second) of competing cross-traffic."""
        if self == CongestionPreset.LOW:
            return 5.0
        elif self == CongestionPreset.MODERATE:
            return 15.0
        elif self == CongestionPreset.HIGH:
            return 30.0
        return 0.0

    @property
    def description(self) -> str:
        if self == CongestionPreset.LOW:
            return "Light competing traffic (5 pkts/s background load)"
        elif self == CongestionPreset.MODERATE:
            return "Moderate competing traffic (15 pkts/s background load)"
        elif self == CongestionPreset.HIGH:
            return "Heavy competing traffic (30 pkts/s background load, high queue backlog)"
        return "Clean dedicated channel (0 pkts/s background load)"


class CrossTrafficGenerator:
    """
    Generates Poisson-distributed background traffic competing for the shared channel.
    """

    def __init__(
        self,
        rate_hz: float = 0.0,
        packet_size_bytes: int = 96,
        seed: int = 101,
    ):
        self.rate_hz = rate_hz
        self.packet_size_bytes = packet_size_bytes
        self.rng = np.random.RandomState(seed)

    def generate_schedule(self, duration_s: float) -> List[Packet]:
        """Pre-computes cross-traffic packet arrivals over the simulation timeline."""
        if self.rate_hz <= 0.0:
            return []

        packets: List[Packet] = []
        mean_interval = 1.0 / self.rate_hz
        t = float(self.rng.exponential(mean_interval))
        seq = 0

        while t < duration_s:
            seq += 1
            pkt = Packet(
                id=f"cross_pkt_{seq}_{t:.3f}",
                sequence_number=seq,
                creation_time=t,
                header_bytes=28,
                custom_payload_bytes=self.packet_size_bytes - 28,
                max_packet_size=128,
                is_cross_traffic=True,
                strategy_name="cross_traffic",
            )
            packets.append(pkt)
            t += float(self.rng.exponential(mean_interval))

        return packets
