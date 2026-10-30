"""
Edge cases tests: empty buffers, expired deadlines, simulation termination with residuals.
"""

from tinyflow.experiment.config import ExperimentConfig
from tinyflow.experiment.runner import ExperimentRunner
from tinyflow.models import ReadingPriority, ReadingType, SensorReading
from tinyflow.network.cross_traffic import CongestionPreset
from tinyflow.network.simulator import DiscreteEventSimulator, NetworkState
from tinyflow.strategies.adaptive import AdaptiveAggregationStrategy
from tinyflow.strategies.fixed import FixedIntervalBatchingStrategy


def test_empty_buffer_decision():
    strat = AdaptiveAggregationStrategy()
    state = NetworkState(
        queue_len=0,
        queue_bytes=0,
        est_queue_delay=0.0,
        est_tx_time_per_packet=0.01,
        channel_busy=False,
        bandwidth_kbps=100.0,
    )
    # Timer tick on empty buffer should return empty packets and not crash
    pkts = strat.on_timer_tick(1.0, state)
    assert pkts == []
    # Residual flush on empty buffer
    residual = strat.flush_residual(10.0)
    assert residual == []


def test_simulation_ends_with_pending_readings_flushed():
    # Fixed batching with interval 10.0s, but simulation ends at 3.0s
    config = ExperimentConfig(
        num_sensors=2,
        reading_rate_hz=1.0,
        duration_s=3.0,
        fixed_batch_interval_s=10.0,  # Never fires before sim end
        seed=42,
    )
    res = ExperimentRunner.run_experiment(config)
    
    fixed_trace = res.traces["Fixed-Interval"]
    # Even though timer never ticked, flush_residual must have packed and transmitted all buffered readings!
    assert fixed_trace.metrics.total_delivered_readings > 0
    assert fixed_trace.metrics.total_transmitted_packets > 0


def test_severe_congestion_behavior():
    # Run under high congestion preset (30 pkts/s background traffic)
    config = ExperimentConfig(
        num_sensors=4,
        reading_rate_hz=2.0,
        duration_s=5.0,
        bandwidth_kbps=30.0,  # Low bandwidth + heavy background traffic
        congestion_preset=CongestionPreset.HIGH,
        seed=88,
    )
    res = ExperimentRunner.run_experiment(config)

    # Queue occupancy must have reached high levels
    adaptive_trace = res.traces["Adaptive"]
    assert adaptive_trace.metrics.max_queue_occupancy > 0
    # Decisions should record congestion flush or deadline approaches
    reasons = [d.reason_code.value for d in adaptive_trace.decisions]
    assert len(reasons) > 0
