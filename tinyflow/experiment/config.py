"""
Experiment Configuration and Preset Definitions.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional
from tinyflow.network.cross_traffic import CongestionPreset


@dataclass
class ExperimentConfig:
    """
    Validated configuration parameters for TinyFlow comparative experiments.
    """
    num_sensors: int = 5
    reading_rate_hz: float = 1.0
    baseline_deadline_s: float = 2.0
    duration_s: float = 20.0
    
    # Network parameters
    bandwidth_kbps: float = 100.0
    propagation_delay_s: float = 0.005
    packet_loss_rate: float = 0.02
    max_queue_packets: int = 50
    congestion_preset: CongestionPreset = CongestionPreset.LOW
    custom_cross_traffic_hz: Optional[float] = None

    # Protocol & packet parameters
    header_bytes: int = 28
    framing_bytes_per_reading: int = 2
    max_packet_size: int = 128

    # Strategy specific
    fixed_batch_interval_s: float = 1.0
    adaptive_max_wait_s: float = 0.8
    adaptive_safety_slack_s: float = 0.25
    adaptive_queue_threshold: int = 4
    adaptive_urgent_flush_high: bool = True

    # Reproducibility
    seed: int = 42
    name: str = "Standard IoT Monitoring Test"

    def get_cross_traffic_rate(self) -> float:
        if self.custom_cross_traffic_hz is not None:
            return max(0.0, self.custom_cross_traffic_hz)
        return self.congestion_preset.packet_rate_hz

    def validate(self) -> None:
        """Validates configuration bounds."""
        if self.num_sensors < 1 or self.num_sensors > 100:
            raise ValueError(f"num_sensors must be between 1 and 100, got {self.num_sensors}")
        if self.reading_rate_hz <= 0 or self.reading_rate_hz > 50:
            raise ValueError(f"reading_rate_hz must be between 0.1 and 50 Hz, got {self.reading_rate_hz}")
        if self.duration_s < 2.0 or self.duration_s > 300:
            raise ValueError(f"duration_s must be between 2 and 300 seconds, got {self.duration_s}")
        if self.bandwidth_kbps < 5.0:
            raise ValueError(f"bandwidth_kbps must be >= 5 kbps, got {self.bandwidth_kbps}")
        if not (0.0 <= self.packet_loss_rate <= 0.9):
            raise ValueError(f"packet_loss_rate must be between 0.0 and 0.9, got {self.packet_loss_rate}")
        if self.max_packet_size < 40 or self.max_packet_size > 1500:
            raise ValueError(f"max_packet_size must be between 40 and 1500 bytes, got {self.max_packet_size}")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["congestion_preset"] = self.congestion_preset.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExperimentConfig:
        d = dict(data)
        if "congestion_preset" in d and isinstance(d["congestion_preset"], str):
            d["congestion_preset"] = CongestionPreset(d["congestion_preset"])
        return cls(**d)
