"""
Synthetic IoT Sensor Generation.
Models realistic temperature, humidity, and soil-moisture sensors with configurable
generation rates, timestamps, priorities, anomalies, and delivery deadlines.
"""

from __future__ import annotations
import math
from typing import List, Optional
import numpy as np

from tinyflow.models import ReadingPriority, ReadingType, SensorReading


class VirtualSensor:
    """
    Simulates an individual IoT sensor node generating synthetic physical readings.
    """

    def __init__(
        self,
        sensor_id: int,
        reading_type: ReadingType,
        rate_hz: float = 1.0,
        baseline_deadline_s: float = 2.0,
        jitter_ratio: float = 0.1,
        anomaly_probability: float = 0.03,
        rng: Optional[np.random.RandomState] = None,
    ):
        self.sensor_id = sensor_id
        self.reading_type = reading_type
        self.rate_hz = rate_hz
        self.baseline_deadline_s = baseline_deadline_s
        self.jitter_ratio = jitter_ratio
        self.anomaly_probability = anomaly_probability
        self.rng = rng or np.random.RandomState(42 + sensor_id)
        
        # Internal state for smooth physical random walk
        self._current_value = self._initial_value()
        self._sequence = 0

    def _initial_value(self) -> float:
        if self.reading_type == ReadingType.TEMPERATURE:
            return float(self.rng.uniform(20.0, 26.0))
        elif self.reading_type == ReadingType.HUMIDITY:
            return float(self.rng.uniform(50.0, 65.0))
        else:  # SOIL_MOISTURE
            return float(self.rng.uniform(30.0, 45.0))

    @property
    def unit(self) -> str:
        if self.reading_type == ReadingType.TEMPERATURE:
            return "°C"
        elif self.reading_type == ReadingType.HUMIDITY:
            return "%RH"
        return "%"

    def generate_reading(self, timestamp: float) -> SensorReading:
        """
        Generate a single sensor measurement at the given timestamp.
        Simulates realistic physical drift, noise, and rare threshold anomalies.
        """
        self._sequence += 1
        is_anomaly = bool(self.rng.random() < self.anomaly_probability)

        if self.reading_type == ReadingType.TEMPERATURE:
            # Diurnal sinusoidal drift + random walk
            diurnal = 3.0 * math.sin(2.0 * math.pi * (timestamp / 300.0))
            drift = float(self.rng.normal(0.0, 0.2))
            base = 24.0 + diurnal + drift
            if is_anomaly:
                # Temperature surge anomaly (e.g. fire or overheating)
                val = base + float(self.rng.uniform(15.0, 30.0))
                priority = ReadingPriority.CRITICAL
            else:
                val = base
                priority = ReadingPriority.HIGH if self.rng.random() < 0.08 else ReadingPriority.NORMAL

        elif self.reading_type == ReadingType.HUMIDITY:
            drift = float(self.rng.normal(0.0, 0.4))
            base = np.clip(self._current_value + drift, 20.0, 95.0)
            if is_anomaly:
                # Sudden humidity drop/spike
                val = float(np.clip(base + self.rng.choice([-25.0, 25.0]), 10.0, 100.0))
                priority = ReadingPriority.HIGH
            else:
                val = float(base)
                priority = ReadingPriority.HIGH if self.rng.random() < 0.05 else ReadingPriority.NORMAL
            self._current_value = val

        else:  # SOIL_MOISTURE
            # Slow drying decay with occasional irrigation spikes
            decay = -0.05
            base = np.clip(self._current_value + decay + float(self.rng.normal(0.0, 0.1)), 10.0, 70.0)
            if is_anomaly:
                # Extreme drought or flood detection
                val = float(np.clip(base - 18.0 if self.rng.random() < 0.5 else base + 25.0, 5.0, 85.0))
                priority = ReadingPriority.HIGH
            else:
                val = float(base)
                priority = ReadingPriority.NORMAL
            self._current_value = val

        val = round(float(val), 2)
        reading_id = f"s{self.sensor_id}_r{self._sequence}_{timestamp:.3f}"
        
        # Deadline calculation scaled by priority urgency
        effective_deadline_window = self.baseline_deadline_s * priority.deadline_factor
        deadline = timestamp + effective_deadline_window

        return SensorReading(
            id=reading_id,
            sensor_id=self.sensor_id,
            timestamp=timestamp,
            reading_type=self.reading_type,
            value=val,
            unit=self.unit,
            priority=priority,
            deadline=deadline,
            payload_bytes=14,
        )


class SensorNetworkGenerator:
    """
    Orchestrates multiple virtual sensors across a simulated IoT environment.
    Generates time-ordered streams of readings over a given duration.
    """

    def __init__(
        self,
        num_sensors: int = 5,
        reading_rate_hz: float = 1.0,
        baseline_deadline_s: float = 2.0,
        seed: int = 42,
    ):
        self.num_sensors = max(1, num_sensors)
        self.reading_rate_hz = max(0.1, reading_rate_hz)
        self.baseline_deadline_s = max(0.2, baseline_deadline_s)
        self.seed = seed
        self.rng = np.random.RandomState(seed)

        types_pool = [ReadingType.TEMPERATURE, ReadingType.HUMIDITY, ReadingType.SOIL_MOISTURE]
        self.sensors: List[VirtualSensor] = []
        for i in range(self.num_sensors):
            stype = types_pool[i % len(types_pool)]
            s_rng = np.random.RandomState(self.seed + 100 * (i + 1))
            self.sensors.append(
                VirtualSensor(
                    sensor_id=i + 1,
                    reading_type=stype,
                    rate_hz=self.reading_rate_hz,
                    baseline_deadline_s=self.baseline_deadline_s,
                    rng=s_rng,
                )
            )

    def generate_workload(self, duration_s: float) -> List[SensorReading]:
        """
        Pre-generate all sensor readings across the simulation timeline.
        Returns a chronologically sorted list of SensorReading objects.
        """
        all_readings: List[SensorReading] = []
        mean_interval = 1.0 / self.reading_rate_hz

        for sensor in self.sensors:
            # Poisson arrival / jittered periodic process
            t = float(sensor.rng.uniform(0.0, mean_interval * 0.5))
            while t < duration_s:
                reading = sensor.generate_reading(t)
                all_readings.append(reading)
                # Exponential inter-arrival time with bounded jitter for realism
                interval = float(sensor.rng.exponential(mean_interval))
                interval = max(0.05, min(interval, mean_interval * 3.0))
                t += interval

        # Sort strictly by timestamp
        all_readings.sort(key=lambda r: r.timestamp)
        return all_readings
