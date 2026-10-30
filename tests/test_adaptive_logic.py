"""
Unit tests for Adaptive Aggregation decision rules and state transitions.
Verifies that all decision codes and texts are strictly backed by actual simulator state.
"""

from tinyflow.models import DecisionAction, DecisionReasonCode, ReadingPriority, ReadingType, SensorReading
from tinyflow.network.simulator import NetworkState
from tinyflow.strategies.adaptive import AdaptiveAggregationStrategy


def _mock_network_state(queue_len: int = 0, est_queue_delay: float = 0.0) -> NetworkState:
    return NetworkState(
        queue_len=queue_len,
        queue_bytes=queue_len * 96,
        est_queue_delay=est_queue_delay,
        est_tx_time_per_packet=0.01,
        channel_busy=False,
        bandwidth_kbps=100.0,
    )


def _make_reading(
    rid: str,
    ts: float,
    priority: ReadingPriority = ReadingPriority.NORMAL,
    deadline_offset: float = 2.0,
) -> SensorReading:
    return SensorReading(
        id=rid,
        sensor_id=1,
        timestamp=ts,
        reading_type=ReadingType.TEMPERATURE,
        value=24.0,
        unit="°C",
        priority=priority,
        deadline=ts + deadline_offset,
        payload_bytes=14,
    )


def test_adaptive_urgent_priority_trigger():
    strat = AdaptiveAggregationStrategy()
    state = _mock_network_state()

    # Normal reading buffered
    r_norm = _make_reading("r_norm", 0.1, ReadingPriority.NORMAL)
    pkts1 = strat.on_reading_arrived(r_norm, 0.1, state)
    assert len(pkts1) == 0
    assert strat.buffer_count == 1
    assert strat.decisions[-1].action == DecisionAction.WAIT

    # Critical reading arrives -> immediate flush
    r_crit = _make_reading("r_crit", 0.2, ReadingPriority.CRITICAL)
    pkts2 = strat.on_reading_arrived(r_crit, 0.2, state)
    assert len(pkts2) == 1
    assert len(pkts2[0].readings) == 2
    assert strat.buffer_count == 0

    last_dec = strat.decisions[-1]
    assert last_dec.action == DecisionAction.TRANSMIT
    assert last_dec.reason_code == DecisionReasonCode.URGENT_PRIORITY_TRIGGER
    assert "Urgent priority reading received" in last_dec.reason_text


def test_adaptive_deadline_approaching_trigger():
    strat = AdaptiveAggregationStrategy(safety_slack_margin_s=0.30)
    state = _mock_network_state()

    # Reading with short deadline (e.g. deadline at 0.5s, generated at 0.0s)
    r = _make_reading("r_tight", 0.0, ReadingPriority.NORMAL, deadline_offset=0.5)
    # At t=0.0, slack is 0.5s > 0.3s -> buffer
    assert strat.on_reading_arrived(r, 0.0, state) == []
    assert strat.buffer_count == 1

    # At t=0.25s, slack is 0.25s <= safety margin (0.30s + network delay) -> timer tick triggers flush
    pkts = strat.on_timer_tick(0.25, state)
    assert len(pkts) == 1
    assert strat.buffer_count == 0

    last_dec = strat.decisions[-1]
    assert last_dec.action == DecisionAction.TRANSMIT
    assert last_dec.reason_code == DecisionReasonCode.DEADLINE_APPROACHING
    assert "Deadline approaching safe margin" in last_dec.reason_text


def test_adaptive_max_wait_exceeded_trigger():
    strat = AdaptiveAggregationStrategy(max_wait_time_s=0.60, safety_slack_margin_s=0.05)
    state = _mock_network_state()

    # Reading generated at 0.0 with huge deadline
    r = _make_reading("r_wait", 0.0, deadline_offset=10.0)
    assert strat.on_reading_arrived(r, 0.0, state) == []

    # At t=0.4s, wait is 0.4s < 0.60s
    assert strat.on_timer_tick(0.4, state) == []
    assert strat.buffer_count == 1

    # At t=0.61s, wait is 0.61s >= 0.60s -> transmit!
    pkts = strat.on_timer_tick(0.61, state)
    assert len(pkts) == 1
    assert strat.buffer_count == 0

    last_dec = strat.decisions[-1]
    assert last_dec.action == DecisionAction.TRANSMIT
    assert last_dec.reason_code == DecisionReasonCode.MAX_WAIT_EXCEEDED
    assert "exceeded dynamic max wait threshold" in last_dec.reason_text


def test_adaptive_mtu_capacity_trigger():
    # Configure max_packet_size = 64 bytes.
    # Header is 28B.
    # Reading 1: 14B + 2B framing = 16B (total 44B)
    # Reading 2: 16B (total 60B)
    # Reading 3: 16B (total 76B > 64B) -> triggers MTU flush
    strat = AdaptiveAggregationStrategy(max_packet_size=64)
    state = _mock_network_state()

    r1 = _make_reading("r1", 0.01, deadline_offset=5.0)
    r2 = _make_reading("r2", 0.02, deadline_offset=5.0)
    r3 = _make_reading("r3", 0.03, deadline_offset=5.0)

    strat.on_reading_arrived(r1, 0.01, state)
    # r2 projected size 60B is near MTU (60 + 16 > 64), so adding r2 will trigger BUFFER_FULL_MTU
    pkts = strat.on_reading_arrived(r2, 0.02, state)
    assert len(pkts) == 1
    assert strat.decisions[-1].reason_code == DecisionReasonCode.BUFFER_FULL_MTU
