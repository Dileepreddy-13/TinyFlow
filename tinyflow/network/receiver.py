"""
IoT Receiver and Packet Decapsulation Engine.
Extracts individual sensor readings from batched packets, validates arrival,
tracks duplicates, delivery latencies, and deadline compliance.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Set
from tinyflow.models import Packet, SensorReading


@dataclass
class DeliveredReadingRecord:
    """
    Log of an individual sensor reading delivered at the receiver.
    """
    reading_id: str
    sensor_id: int
    reading_type: str
    value: float
    unit: str
    priority: str
    generation_time: float
    delivery_time: float
    deadline: float
    e2e_delay: float
    met_deadline: bool
    slack_at_delivery: float
    packet_id: str
    batch_size: int


class Receiver:
    """
    Receiver node (IoT Gateway / Cloud Sink) terminating the wireless link.
    """

    def __init__(self):
        self.delivered_records: List[DeliveredReadingRecord] = []
        self.delivered_packets: List[Packet] = []
        self.seen_reading_ids: Set[str] = set()
        self.seen_packet_ids: Set[str] = set()
        self.duplicate_readings_count = 0
        self.duplicate_packets_count = 0

    def receive_packet(self, packet: Packet, delivery_time: float) -> List[DeliveredReadingRecord]:
        """
        Processes a successfully arrived packet over the channel.
        Decapsulates batched readings and records arrival metrics.
        """
        packet.delivery_time = delivery_time
        
        if packet.id in self.seen_packet_ids:
            self.duplicate_packets_count += 1
            return []
        self.seen_packet_ids.add(packet.id)
        self.delivered_packets.append(packet)

        # Ignore cross-traffic background packets at the IoT application receiver
        if packet.is_cross_traffic:
            return []

        batch_records: List[DeliveredReadingRecord] = []
        batch_size = len(packet.readings)

        for reading in packet.readings:
            if reading.id in self.seen_reading_ids:
                self.duplicate_readings_count += 1
                continue
            self.seen_reading_ids.add(reading.id)

            e2e_delay = max(0.0, delivery_time - reading.timestamp)
            slack = reading.deadline - delivery_time
            met_deadline = delivery_time <= reading.deadline

            rec = DeliveredReadingRecord(
                reading_id=reading.id,
                sensor_id=reading.sensor_id,
                reading_type=reading.reading_type.value,
                value=reading.value,
                unit=reading.unit,
                priority=reading.priority.name,
                generation_time=reading.timestamp,
                delivery_time=delivery_time,
                deadline=reading.deadline,
                e2e_delay=e2e_delay,
                met_deadline=met_deadline,
                slack_at_delivery=slack,
                packet_id=packet.id,
                batch_size=batch_size,
            )
            self.delivered_records.append(rec)
            batch_records.append(rec)

        return batch_records
