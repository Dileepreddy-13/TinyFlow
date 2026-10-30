"""
Experiment Execution Engine.
Executes all three aggregation strategies under strictly identical workloads,
channel conditions, and metric definitions.
"""

from __future__ import annotations
import copy
from dataclasses import dataclass, field
import datetime
import uuid
from typing import Dict, List, Optional
import numpy as np

from tinyflow.experiment.config import ExperimentConfig
from tinyflow.metrics.calculator import StrategyMetrics, compute_metrics
from tinyflow.models import DecisionRecord, Packet, SensorReading
from tinyflow.network.cross_traffic import CrossTrafficGenerator
from tinyflow.network.receiver import DeliveredReadingRecord
from tinyflow.network.simulator import DiscreteEventSimulator
from tinyflow.sensor import SensorNetworkGenerator
from tinyflow.strategies.adaptive import AdaptiveAggregationStrategy
from tinyflow.strategies.fixed import FixedIntervalBatchingStrategy
from tinyflow.strategies.immediate import ImmediateStrategy


@dataclass
class StrategyExecutionTrace:
    """Detailed traces and data for one strategy run."""
    metrics: StrategyMetrics
    decisions: List[DecisionRecord]
    delivered_records: List[DeliveredReadingRecord]
    queue_history: List[tuple[float, int, int]]
    transmitted_packets: List[Packet]


@dataclass
class ExperimentRunResult:
    """Complete results of comparing all three strategies on an identical workload."""
    experiment_id: str
    config: ExperimentConfig
    created_at: str
    workload: List[SensorReading]
    cross_traffic: List[Packet]
    traces: Dict[str, StrategyExecutionTrace]

    @property
    def metrics(self) -> Dict[str, StrategyMetrics]:
        return {name: trace.metrics for name, trace in self.traces.items()}

    def get_summary_comparison(self) -> List[Dict[str, Any]]:
        rows = []
        for name, trace in self.traces.items():
            m = trace.metrics
            rows.append({
                "Strategy": name,
                "Header Overhead (%)": m.header_overhead_percent,
                "Throughput (bytes/s)": m.useful_throughput_bps,
                "Mean Delay (ms)": m.mean_e2e_delay_ms,
                "P95 Delay (ms)": m.p95_e2e_delay_ms,
                "Deadline Miss Rate (%)": m.deadline_miss_rate_percent,
                "Energy Est (mJ)": m.total_energy_estimate_mj,
                "Avg Batch Size": m.avg_batch_size,
                "Delivered Readings": m.total_delivered_readings,
                "Total Readings": m.total_generated_readings,
            })
        return rows


class ExperimentRunner:
    """
    Orchestrates comparative simulations.
    Guarantees strict fairness: identical generated readings, identical cross-traffic,
    and identical random seed per channel trial.
    """

    @classmethod
    def run_experiment(cls, config: ExperimentConfig) -> ExperimentRunResult:
        config.validate()
        exp_id = f"exp_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        created_at = datetime.datetime.now().isoformat()

        # 1. Pre-generate identical sensor reading workload
        sensor_gen = SensorNetworkGenerator(
            num_sensors=config.num_sensors,
            reading_rate_hz=config.reading_rate_hz,
            baseline_deadline_s=config.baseline_deadline_s,
            seed=config.seed,
        )
        workload = sensor_gen.generate_workload(config.duration_s)

        # 2. Pre-generate identical competing background traffic
        cross_rate = config.get_cross_traffic_rate()
        cross_gen = CrossTrafficGenerator(
            rate_hz=cross_rate,
            seed=config.seed + 999,
        )
        cross_traffic_template = cross_gen.generate_schedule(config.duration_s)

        # 3. Instantiate strategies
        strategies = [
            ImmediateStrategy(
                header_bytes=config.header_bytes,
                framing_bytes_per_reading=config.framing_bytes_per_reading,
                max_packet_size=config.max_packet_size,
            ),
            FixedIntervalBatchingStrategy(
                batch_interval_s=config.fixed_batch_interval_s,
                header_bytes=config.header_bytes,
                framing_bytes_per_reading=config.framing_bytes_per_reading,
                max_packet_size=config.max_packet_size,
            ),
            AdaptiveAggregationStrategy(
                max_wait_time_s=config.adaptive_max_wait_s,
                safety_slack_margin_s=config.adaptive_safety_slack_s,
                congestion_queue_threshold=config.adaptive_queue_threshold,
                urgent_flush_high=config.adaptive_urgent_flush_high,
                header_bytes=config.header_bytes,
                framing_bytes_per_reading=config.framing_bytes_per_reading,
                max_packet_size=config.max_packet_size,
            ),
        ]

        traces: Dict[str, StrategyExecutionTrace] = {}

        # 4. Run each strategy through its own clean simulator instance
        for strat in strategies:
            sim = DiscreteEventSimulator(
                bandwidth_kbps=config.bandwidth_kbps,
                propagation_delay_s=config.propagation_delay_s,
                packet_loss_rate=config.packet_loss_rate,
                max_queue_packets=config.max_queue_packets,
                seed=config.seed,  # Exact same channel loss seed
            )

            # Deep-copy readings and cross-traffic packets so mutations in one strategy do not taint another
            workload_copy = [
                SensorReading(
                    id=r.id,
                    sensor_id=r.sensor_id,
                    timestamp=r.timestamp,
                    reading_type=r.reading_type,
                    value=r.value,
                    unit=r.unit,
                    priority=r.priority,
                    deadline=r.deadline,
                    payload_bytes=r.payload_bytes,
                )
                for r in workload
            ]

            cross_traffic_copy = [
                Packet(
                    id=f"{strat.name}_{cp.id}",
                    sequence_number=cp.sequence_number,
                    creation_time=cp.creation_time,
                    header_bytes=cp.header_bytes,
                    custom_payload_bytes=cp.custom_payload_bytes,
                    max_packet_size=cp.max_packet_size,
                    is_cross_traffic=True,
                    strategy_name="cross_traffic",
                )
                for cp in cross_traffic_template
            ]

            timer_interval = (
                config.fixed_batch_interval_s
                if isinstance(strat, FixedIntervalBatchingStrategy)
                else 0.05
            )

            receiver = sim.run(
                strategy=strat,
                readings_workload=workload_copy,
                cross_traffic_packets=cross_traffic_copy,
                duration_s=config.duration_s,
                timer_interval_s=timer_interval,
            )

            metrics = compute_metrics(
                strategy_name=strat.name,
                all_readings=workload_copy,
                transmitted_packets=sim.all_generated_packets,
                dropped_packets=sim.dropped_packets,
                receiver=receiver,
                queue_history=sim.queue_history,
                duration_s=config.duration_s,
            )

            traces[strat.name] = StrategyExecutionTrace(
                metrics=metrics,
                decisions=strat.decisions,
                delivered_records=receiver.delivered_records,
                queue_history=sim.queue_history,
                transmitted_packets=sim.all_generated_packets,
            )

        return ExperimentRunResult(
            experiment_id=exp_id,
            config=config,
            created_at=created_at,
            workload=workload,
            cross_traffic=cross_traffic_template,
            traces=traces,
        )

    @classmethod
    def run_multi_seed(
        cls, base_config: ExperimentConfig, seeds: List[int]
    ) -> Dict[str, Dict[str, tuple[float, float]]]:
        """
        Runs repeated experiments with multiple seeds.
        Computes mean and sample standard deviation for key metrics per strategy.
        """
        aggregated: Dict[str, Dict[str, List[float]]] = {
            "Immediate": {"overhead": [], "delay": [], "throughput": [], "miss_rate": [], "energy": []},
            "Fixed-Interval": {"overhead": [], "delay": [], "throughput": [], "miss_rate": [], "energy": []},
            "Adaptive": {"overhead": [], "delay": [], "throughput": [], "miss_rate": [], "energy": []},
        }

        for s in seeds:
            cfg = copy.deepcopy(base_config)
            cfg.seed = s
            res = cls.run_experiment(cfg)
            for strat_name, trace in res.traces.items():
                m = trace.metrics
                aggregated[strat_name]["overhead"].append(m.header_overhead_percent)
                aggregated[strat_name]["delay"].append(m.mean_e2e_delay_ms)
                aggregated[strat_name]["throughput"].append(m.useful_throughput_bps)
                aggregated[strat_name]["miss_rate"].append(m.deadline_miss_rate_percent)
                aggregated[strat_name]["energy"].append(m.total_energy_estimate_mj)

        summary: Dict[str, Dict[str, tuple[float, float]]] = {}
        for strat_name, metrics_dict in aggregated.items():
            summary[strat_name] = {}
            for metric_key, values in metrics_dict.items():
                mean_val = float(np.mean(values))
                std_val = float(np.std(values)) if len(values) > 1 else 0.0
                summary[strat_name][metric_key] = (round(mean_val, 2), round(std_val, 2))

        return summary
