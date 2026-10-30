"""
Unit tests for VirtualSensor and SensorNetworkGenerator.
"""

import pytest
import numpy as np

from tinyflow.models import ReadingPriority, ReadingType
from tinyflow.sensor import VirtualSensor, SensorNetworkGenerator


def test_virtual_sensor_generation():
    sensor = VirtualSensor(
        sensor_id=1,
        reading_type=ReadingType.TEMPERATURE,
        rate_hz=1.0,
        baseline_deadline_s=2.0,
    )
    reading = sensor.generate_reading(timestamp=1.5)

    assert reading.sensor_id == 1
    assert reading.reading_type == ReadingType.TEMPERATURE
    assert reading.timestamp == 1.5
    assert reading.unit == "°C"
    assert 10.0 <= reading.value <= 60.0
    assert reading.deadline > reading.timestamp
    assert reading.payload_bytes == 14


def test_priority_deadline_scaling():
    sensor = VirtualSensor(
        sensor_id=2,
        reading_type=ReadingType.HUMIDITY,
        baseline_deadline_s=2.0,
    )
    # Generate multiple readings to verify deadline window is bounded
    readings = [sensor.generate_reading(t) for t in [0.0, 1.0, 2.0]]
    for r in readings:
        diff = r.deadline - r.timestamp
        if r.priority == ReadingPriority.CRITICAL:
            assert pytest.approx(diff, 0.01) == 2.0 * 0.4
        elif r.priority == ReadingPriority.HIGH:
            assert pytest.approx(diff, 0.01) == 2.0 * 0.7
        else:
            assert pytest.approx(diff, 0.01) == 2.0 * 1.0


def test_sensor_network_generator_workload():
    generator = SensorNetworkGenerator(
        num_sensors=4,
        reading_rate_hz=2.0,
        baseline_deadline_s=1.5,
        seed=42,
    )
    duration = 5.0
    workload = generator.generate_workload(duration_s=duration)

    assert len(workload) > 0
    # Must be chronologically sorted
    timestamps = [r.timestamp for r in workload]
    assert timestamps == sorted(timestamps)
    assert all(t <= duration for t in timestamps)


def test_sensor_generator_reproducibility():
    gen1 = SensorNetworkGenerator(num_sensors=3, reading_rate_hz=1.0, seed=123)
    gen2 = SensorNetworkGenerator(num_sensors=3, reading_rate_hz=1.0, seed=123)

    workload1 = gen1.generate_workload(duration_s=10.0)
    workload2 = gen2.generate_workload(duration_s=10.0)

    assert len(workload1) == len(workload2)
    for r1, r2 in zip(workload1, workload2):
        assert r1.id == r2.id
        assert r1.timestamp == r2.timestamp
        assert r1.value == r2.value
        assert r1.priority == r2.priority
