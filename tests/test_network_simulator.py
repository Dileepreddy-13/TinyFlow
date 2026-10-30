"""
Unit tests for DiscreteEventSimulator, channel bandwidth, queues, and receiver.
"""

from tinyflow.models import Packet, ReadingPriority, ReadingType, SensorReading
from tinyflow.network.receiver import Receiver
from tinyflow.network.simulator import DiscreteEventSimulator
from tinyflow.strategies.immediate import ImmediateStrategy


def _make_reading(rid: str, ts: float) -> SensorReading:
    return SensorReading(
        id=rid,
        sensor_id=1,
        timestamp=ts,
        reading_type=ReadingType.TEMPERATURE,
        value=25.0,
        unit="°C",
        priority=ReadingPriority.NORMAL,
        deadline=ts + 2.0,
        payload_bytes=14,
    )


def test_bandwidth_delay_transmission():
    # 100 kbps = 12,500 bytes/sec
    # A 125-byte packet should take exactly (125 * 8) / 100000 = 0.010 seconds (10 ms)
    sim = DiscreteEventSimulator(bandwidth_kbps=100.0, propagation_delay_s=0.005, packet_loss_rate=0.0)
    strat = ImmediateStrategy(header_bytes=28, max_packet_size=128)

    # 1 reading: total bytes = 28 + (14 + 2) = 44 bytes
    r1 = _make_reading("r1", 0.0)
    receiver = sim.run(strat, [r1], [], duration_s=1.0)

    assert len(receiver.delivered_records) == 1
    rec = receiver.delivered_records[0]
    # Expected tx time: (44 * 8) / 100000 = 0.00352s + prop delay 0.005s = 0.00852s
    expected_delivery = 0.0 + (44 * 8 / 100000.0) + 0.005
    assert abs(rec.delivery_time - expected_delivery) < 1e-4
    assert rec.met_deadline is True


def test_channel_packet_loss():
    # Test 100% loss rate drops all packets
    sim_lossy = DiscreteEventSimulator(bandwidth_kbps=100.0, packet_loss_rate=1.0)
    strat = ImmediateStrategy()
    r = _make_reading("r_lost", 0.0)
    receiver = sim_lossy.run(strat, [r], [], duration_s=1.0)

    assert len(receiver.delivered_records) == 0
    assert len(sim_lossy.dropped_packets) == 1
    assert sim_lossy.dropped_packets[0].drop_reason == "CHANNEL_LOSS"


def test_queue_overflow_drop():
    # Max queue limit 2 packets
    sim = DiscreteEventSimulator(bandwidth_kbps=10.0, max_queue_packets=2)
    strat = ImmediateStrategy()
    # Send 5 readings simultaneously at t=0.0
    readings = [_make_reading(f"r_{i}", 0.0) for i in range(5)]
    receiver = sim.run(strat, readings, [], duration_s=5.0)

    # 1 in transmission + 2 in queue = 3 accepted, 2 dropped due to queue overflow
    overflow_drops = [p for p in sim.dropped_packets if p.drop_reason == "QUEUE_OVERFLOW"]
    assert len(overflow_drops) == 2
