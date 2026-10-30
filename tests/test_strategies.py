"""
Unit tests for Immediate and FixedInterval aggregation strategies.
"""

from tinyflow.models import DecisionAction, ReadingPriority, ReadingType, SensorReading
from tinyflow.network.simulator import NetworkState
from tinyflow.strategies.immediate import ImmediateStrategy
from tinyflow.strategies.fixed import FixedIntervalBatchingStrategy


def _mock_network_state() -> NetworkState:
    return NetworkState(
        queue_len=0,
        queue_bytes=0,
        est_queue_delay=0.0,
        est_tx_time_per_packet=0.01,
        channel_busy=False,
        bandwidth_kbps=100.0,
    )


def _make_reading(rid: str, ts: float) -> SensorReading:
    return SensorReading(
        id=rid,
        sensor_id=1,
        timestamp=ts,
        reading_type=ReadingType.TEMPERATURE,
        value=22.5,
        unit="°C",
        priority=ReadingPriority.NORMAL,
        deadline=ts + 2.0,
        payload_bytes=14,
    )


def test_immediate_strategy():
    strat = ImmediateStrategy(header_bytes=28, max_packet_size=128)
    state = _mock_network_state()

    r1 = _make_reading("r1", 0.1)
    pkts = strat.on_reading_arrived(r1, 0.1, state)

    assert len(pkts) == 1
    assert len(pkts[0].readings) == 1
    assert pkts[0].readings[0].id == "r1"
    assert strat.buffer_count == 0
    assert len(strat.decisions) == 1
    assert strat.decisions[0].action == DecisionAction.TRANSMIT


def test_fixed_interval_batching_strategy():
    strat = FixedIntervalBatchingStrategy(batch_interval_s=1.0, header_bytes=28, max_packet_size=128)
    state = _mock_network_state()

    # Reading arrivals within interval should be buffered
    r1 = _make_reading("r1", 0.1)
    r2 = _make_reading("r2", 0.3)
    r3 = _make_reading("r3", 0.7)

    assert strat.on_reading_arrived(r1, 0.1, state) == []
    assert strat.on_reading_arrived(r2, 0.3, state) == []
    assert strat.on_reading_arrived(r3, 0.7, state) == []
    assert strat.buffer_count == 3

    # Timer tick at 1.0s should flush the batch
    pkts = strat.on_timer_tick(1.0, state)
    assert len(pkts) == 1
    assert len(pkts[0].readings) == 3
    assert strat.buffer_count == 0


def test_fixed_batching_mtu_overflow_flush():
    # Configure tiny MTU: header 28B + reading (14B+2B) = 44B.
    # A second reading would make it 60B. Set max_packet_size=50B so 2nd reading triggers flush.
    strat = FixedIntervalBatchingStrategy(batch_interval_s=5.0, header_bytes=28, max_packet_size=50)
    state = _mock_network_state()

    r1 = _make_reading("r1", 0.1)
    r2 = _make_reading("r2", 0.2)

    assert strat.on_reading_arrived(r1, 0.1, state) == []
    assert strat.buffer_count == 1

    # Adding r2 should trigger MTU flush of r1, buffering r2
    pkts = strat.on_reading_arrived(r2, 0.2, state)
    assert len(pkts) == 1
    assert len(pkts[0].readings) == 1
    assert pkts[0].readings[0].id == "r1"
    assert strat.buffer_count == 1
    assert strat.buffer[0].id == "r2"
