"""
Unit tests for Packet modeling and MTU calculations.
"""

from tinyflow.models import Packet, ReadingPriority, ReadingType, SensorReading


def _make_reading(reading_id: str, ts: float = 0.0, payload_bytes: int = 14) -> SensorReading:
    return SensorReading(
        id=reading_id,
        sensor_id=1,
        timestamp=ts,
        reading_type=ReadingType.TEMPERATURE,
        value=25.0,
        unit="°C",
        priority=ReadingPriority.NORMAL,
        deadline=ts + 2.0,
        payload_bytes=payload_bytes,
    )


def test_packet_payload_and_total_bytes():
    r1 = _make_reading("r1", 0.0, 14)
    r2 = _make_reading("r2", 0.1, 14)
    
    pkt = Packet(
        id="pkt_test_1",
        sequence_number=1,
        creation_time=0.2,
        readings=[r1, r2],
        header_bytes=28,
        framing_bytes_per_reading=2,
        max_packet_size=128,
    )

    # Payload: 2 readings * 14B + 2 readings * 2B framing = 32B
    assert pkt.payload_bytes == 32
    # Total: 28B header + 32B payload = 60B
    assert pkt.total_bytes == 60
    assert pkt.reading_count == 2
    # Header overhead ratio: 28 / 60
    assert pytest_approx(pkt.header_overhead_ratio, 28 / 60)


def pytest_approx(a, b, tol=1e-5):
    return abs(a - b) <= tol


def test_packet_can_fit_reading():
    r1 = _make_reading("r1", 0.0, 14)
    pkt = Packet(
        id="pkt_mtu_test",
        sequence_number=1,
        creation_time=0.0,
        readings=[r1],
        header_bytes=28,
        framing_bytes_per_reading=2,
        max_packet_size=50,  # Tiny MTU
    )

    # Current size: 28 + (14 + 2) = 44 bytes.
    # Adding another reading would need 44 + 14 + 2 = 60 bytes > 50 MTU
    r2 = _make_reading("r2", 0.1, 14)
    assert not pkt.can_fit_reading(r2)
