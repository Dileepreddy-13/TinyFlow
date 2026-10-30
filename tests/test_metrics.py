"""
Unit tests for metric computations and energy model equations.
"""

from tinyflow.metrics.calculator import compute_metrics
from tinyflow.metrics.energy_model import EnergyModelParameters, estimate_energy_consumption
from tinyflow.models import Packet, ReadingPriority, ReadingType, SensorReading
from tinyflow.network.receiver import Receiver


def test_header_overhead_and_useful_throughput():
    r1 = SensorReading("r1", 1, 0.0, ReadingType.TEMPERATURE, 20.0, "°C", ReadingPriority.NORMAL, 2.0, 14)
    r2 = SensorReading("r2", 1, 0.0, ReadingType.TEMPERATURE, 21.0, "°C", ReadingPriority.NORMAL, 2.0, 14)

    pkt = Packet(
        id="pkt1",
        sequence_number=1,
        creation_time=0.0,
        readings=[r1, r2],
        header_bytes=28,
        framing_bytes_per_reading=2,
        max_packet_size=128,
    )
    # Payload = 2*14 + 2*2 = 32B. Total = 28 + 32 = 60B.
    # Overhead = 28 / 60 * 100 = 46.67%

    receiver = Receiver()
    receiver.receive_packet(pkt, delivery_time=0.05)

    metrics = compute_metrics(
        strategy_name="TestBatch",
        all_readings=[r1, r2],
        transmitted_packets=[pkt],
        dropped_packets=[],
        receiver=receiver,
        queue_history=[(0.0, 1, 60)],
        duration_s=1.0,
    )

    assert abs(metrics.header_overhead_percent - (28 / 60 * 100)) < 0.1
    # Useful throughput: 28 bytes / 1.0s = 28 bytes/s (payload bytes of r1+r2 = 14+14 = 28)
    assert metrics.useful_throughput_bps == 28.0
    assert metrics.total_delivered_readings == 2
    assert metrics.deadline_miss_rate_percent == 0.0


def test_energy_model_equations():
    params = EnergyModelParameters(
        tx_startup_energy_mj=0.050,
        tx_energy_per_byte_mj=0.0012,
        proc_energy_per_reading_mj=0.0004,
        batch_pack_energy_mj=0.0008,
    )
    # 2 packets, 120 total bytes, 4 readings generated, 4 readings delivered
    res = estimate_energy_consumption(
        num_packets_transmitted=2,
        total_bytes_transmitted=120,
        num_readings_generated=4,
        num_readings_delivered=4,
        params=params,
    )

    expected_radio = (2 * 0.050) + (120 * 0.0012)  # 0.100 + 0.144 = 0.244 mJ
    expected_mcu = (4 * 0.0004) + (2 * 0.0008)      # 0.0016 + 0.0016 = 0.0032 mJ
    expected_total = expected_radio + expected_mcu    # 0.2472 mJ

    assert abs(res["radio_energy_mj"] - expected_radio) < 1e-4
    assert abs(res["mcu_energy_mj"] - expected_mcu) < 1e-4
    assert abs(res["total_energy_mj"] - expected_total) < 1e-4
