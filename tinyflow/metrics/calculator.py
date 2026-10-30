"""
Performance metrics calculator for TinyFlow IoT simulation.
Calculates header overhead, throughput, latency distributions, deadline misses, and energy estimates.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

from tinyflow.models import Packet, SensorReading
from tinyflow.network.receiver import DeliveredReadingRecord, Receiver
from tinyflow.metrics.energy_model import estimate_energy_consumption


@dataclass
class StrategyMetrics:
    """
    Comprehensive performance metrics container for an aggregation strategy evaluation.
    """
    strategy_name: str
    duration_s: float
    total_generated_readings: int
    total_transmitted_packets: int
    total_delivered_readings: int
    total_delivered_packets: int
    total_lost_packets: int
    total_undelivered_readings: int
    
    # Byte metrics
    total_bytes_transmitted: int
    total_header_bytes_transmitted: int
    total_payload_bytes_transmitted: int
    total_useful_payload_bytes_delivered: int

    # Core performance indicators
    header_overhead_percent: float
    useful_throughput_bps: float
    useful_throughput_kbps: float

    # Delay metrics (milliseconds)
    mean_e2e_delay_ms: float
    median_e2e_delay_ms: float
    p95_e2e_delay_ms: float
    min_e2e_delay_ms: float
    max_e2e_delay_ms: float

    # Deadline metrics
    deadline_miss_rate_percent: float
    delivered_on_time_count: int
    delivered_late_count: int
    delivered_late_percent: float
    lost_or_dropped_count: int
    lost_or_dropped_percent: float

    # Batching and queue metrics
    avg_batch_size: float
    max_queue_occupancy: int
    mean_queue_occupancy: float

    # Energy model estimates (mJ)
    total_energy_estimate_mj: float
    energy_per_delivered_reading_mj: float
    radio_energy_mj: float
    mcu_energy_mj: float

    # Raw traces for plotting
    e2e_delays_s: List[float] = field(default_factory=list)
    batch_sizes: List[int] = field(default_factory=list)
    packet_timeline: List[dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Exclude large raw traces from json export if needed
        d.pop("e2e_delays_s", None)
        d.pop("batch_sizes", None)
        d.pop("packet_timeline", None)
        return d


def compute_metrics(
    strategy_name: str,
    all_readings: List[SensorReading],
    transmitted_packets: List[Packet],
    dropped_packets: List[Packet],
    receiver: Receiver,
    queue_history: List[tuple[float, int, int]],
    duration_s: float,
) -> StrategyMetrics:
    """
    Calculates verified metrics with explicitly documented mathematical formulas.
    """
    total_gen = len(all_readings)
    delivered_recs = receiver.delivered_records
    total_delivered_readings = len(delivered_recs)

    # Filter out cross-traffic packets for IoT application metrics
    iot_transmitted_pkts = [p for p in transmitted_packets if not p.is_cross_traffic]
    iot_dropped_pkts = [p for p in dropped_packets if not p.is_cross_traffic]

    total_bytes_tx = sum(p.total_bytes for p in iot_transmitted_pkts)
    total_header_tx = sum(p.header_bytes for p in iot_transmitted_pkts)
    total_payload_tx = sum(p.payload_bytes for p in iot_transmitted_pkts)

    # Header overhead formula: (Header Bytes / Total Bytes Transmitted) * 100
    overhead_pct = (
        (total_header_tx / total_bytes_tx * 100.0) if total_bytes_tx > 0 else 0.0
    )

    # Useful throughput formula: Delivered payload bytes / duration
    useful_payload_bytes = sum(r.payload_bytes for r in all_readings if r.id in receiver.seen_reading_ids)
    useful_throughput_bps = (useful_payload_bytes / duration_s) if duration_s > 0 else 0.0
    useful_throughput_kbps = (useful_throughput_bps * 8.0) / 1000.0

    # Delay distribution
    delays_ms = [r.e2e_delay * 1000.0 for r in delivered_recs]
    if delays_ms:
        mean_delay = float(np.mean(delays_ms))
        median_delay = float(np.median(delays_ms))
        p95_delay = float(np.percentile(delays_ms, 95))
        min_delay = float(np.min(delays_ms))
        max_delay = float(np.max(delays_ms))
    else:
        mean_delay = median_delay = p95_delay = min_delay = max_delay = 0.0

    # Deadline compliance
    on_time = [r for r in delivered_recs if r.met_deadline]
    late = [r for r in delivered_recs if not r.met_deadline]
    on_time_count = len(on_time)
    late_count = len(late)
    
    # Readings lost or never delivered (still buffered or lost on link)
    lost_or_dropped_count = max(0, total_gen - total_delivered_readings)
    total_missed = late_count + lost_or_dropped_count
    deadline_miss_rate = (total_missed / total_gen * 100.0) if total_gen > 0 else 0.0
    late_pct = (late_count / total_gen * 100.0) if total_gen > 0 else 0.0
    lost_pct = (lost_or_dropped_count / total_gen * 100.0) if total_gen > 0 else 0.0

    # Batch sizes
    batch_sizes = [len(p.readings) for p in iot_transmitted_pkts if p.readings]
    avg_batch = float(np.mean(batch_sizes)) if batch_sizes else 0.0

    # Queue stats
    if queue_history:
        q_counts = [entry[1] for entry in queue_history]
        max_q = int(np.max(q_counts))
        mean_q = float(np.mean(q_counts))
    else:
        max_q = 0
        mean_q = 0.0

    # Energy model
    energy_results = estimate_energy_consumption(
        num_packets_transmitted=len(iot_transmitted_pkts),
        total_bytes_transmitted=total_bytes_tx,
        num_readings_generated=total_gen,
        num_readings_delivered=total_delivered_readings,
    )

    # Timeline trace for visual inspection
    timeline = []
    for p in iot_transmitted_pkts[:250]:  # Cap for UI efficiency
        timeline.append({
            "packet_id": p.id,
            "seq": p.sequence_number,
            "tx_start": p.transmission_start_time,
            "tx_end": p.transmission_end_time,
            "readings_count": len(p.readings),
            "total_bytes": p.total_bytes,
            "was_dropped": p.was_dropped,
            "drop_reason": p.drop_reason,
        })

    return StrategyMetrics(
        strategy_name=strategy_name,
        duration_s=duration_s,
        total_generated_readings=total_gen,
        total_transmitted_packets=len(iot_transmitted_pkts),
        total_delivered_readings=total_delivered_readings,
        total_delivered_packets=len(receiver.delivered_packets),
        total_lost_packets=len(iot_dropped_pkts),
        total_undelivered_readings=lost_or_dropped_count,
        total_bytes_transmitted=total_bytes_tx,
        total_header_bytes_transmitted=total_header_tx,
        total_payload_bytes_transmitted=total_payload_tx,
        total_useful_payload_bytes_delivered=useful_payload_bytes,
        header_overhead_percent=round(overhead_pct, 2),
        useful_throughput_bps=round(useful_throughput_bps, 2),
        useful_throughput_kbps=round(useful_throughput_kbps, 2),
        mean_e2e_delay_ms=round(mean_delay, 2),
        median_e2e_delay_ms=round(median_delay, 2),
        p95_e2e_delay_ms=round(p95_delay, 2),
        min_e2e_delay_ms=round(min_delay, 2),
        max_e2e_delay_ms=round(max_delay, 2),
        deadline_miss_rate_percent=round(deadline_miss_rate, 2),
        delivered_on_time_count=on_time_count,
        delivered_late_count=late_count,
        delivered_late_percent=round(late_pct, 2),
        lost_or_dropped_count=lost_or_dropped_count,
        lost_or_dropped_percent=round(lost_pct, 2),
        avg_batch_size=round(avg_batch, 2),
        max_queue_occupancy=max_q,
        mean_queue_occupancy=round(mean_q, 2),
        total_energy_estimate_mj=energy_results["total_energy_mj"],
        energy_per_delivered_reading_mj=energy_results["energy_per_delivered_reading_mj"],
        radio_energy_mj=energy_results["radio_energy_mj"],
        mcu_energy_mj=energy_results["mcu_energy_mj"],
        e2e_delays_s=[r.e2e_delay for r in delivered_recs],
        batch_sizes=batch_sizes,
        packet_timeline=timeline,
    )
