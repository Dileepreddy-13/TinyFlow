"""
Unit tests for end-to-end experiment reproducibility across identical seeds.
"""

from tinyflow.experiment.config import ExperimentConfig
from tinyflow.experiment.runner import ExperimentRunner


def test_experiment_reproducibility_with_identical_seed():
    config1 = ExperimentConfig(
        num_sensors=3,
        reading_rate_hz=1.0,
        duration_s=5.0,
        seed=100,
        bandwidth_kbps=80.0,
        packet_loss_rate=0.05,
    )
    config2 = ExperimentConfig(
        num_sensors=3,
        reading_rate_hz=1.0,
        duration_s=5.0,
        seed=100,
        bandwidth_kbps=80.0,
        packet_loss_rate=0.05,
    )

    res1 = ExperimentRunner.run_experiment(config1)
    res2 = ExperimentRunner.run_experiment(config2)

    # Generated workload must match exactly
    assert len(res1.workload) == len(res2.workload)
    for w1, w2 in zip(res1.workload, res2.workload):
        assert w1.id == w2.id
        assert w1.timestamp == w2.timestamp
        assert w1.value == w2.value

    # All strategy metrics must match identically
    for strat in ["Immediate", "Fixed-Interval", "Adaptive"]:
        m1 = res1.traces[strat].metrics
        m2 = res2.traces[strat].metrics

        assert m1.total_generated_readings == m2.total_generated_readings
        assert m1.total_delivered_readings == m2.total_delivered_readings
        assert m1.total_transmitted_packets == m2.total_transmitted_packets
        assert m1.header_overhead_percent == m2.header_overhead_percent
        assert m1.mean_e2e_delay_ms == m2.mean_e2e_delay_ms
        assert m1.deadline_miss_rate_percent == m2.deadline_miss_rate_percent
        assert m1.total_energy_estimate_mj == m2.total_energy_estimate_mj
