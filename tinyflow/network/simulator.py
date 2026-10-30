"""
Discrete-Event Network Simulator for TinyFlow.
Models physical link bandwidth, transmission delay, FIFO packet queueing,
competing cross-traffic congestion, and channel packet loss.
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
import heapq
from typing import Any, Callable, Deque, List, Optional
import numpy as np

from tinyflow.models import Packet, SensorReading
from tinyflow.network.cross_traffic import CrossTrafficGenerator
from tinyflow.network.receiver import Receiver
from tinyflow.strategies.base import BaseAggregationStrategy


@dataclass
class NetworkState:
    """Snapshot of channel conditions provided to aggregation strategies."""
    queue_len: int
    queue_bytes: int
    est_queue_delay: float
    est_tx_time_per_packet: float
    channel_busy: bool
    bandwidth_kbps: float


@dataclass(order=True)
class Event:
    """Discrete simulation event scheduled in the event priority queue."""
    timestamp: float
    priority_order: int
    event_type: str = field(compare=False)
    data: Any = field(compare=False, default=None)


class DiscreteEventSimulator:
    """
    High-fidelity discrete-event simulator for IoT packet transmission over a shared channel.
    """

    def __init__(
        self,
        bandwidth_kbps: float = 100.0,
        propagation_delay_s: float = 0.005,
        packet_loss_rate: float = 0.0,
        max_queue_packets: int = 50,
        seed: int = 42,
    ):
        self.bandwidth_kbps = max(10.0, bandwidth_kbps)
        self.propagation_delay_s = max(0.0, propagation_delay_s)
        self.packet_loss_rate = min(0.99, max(0.0, packet_loss_rate))
        self.max_queue_packets = max(1, max_queue_packets)
        self.seed = seed
        self.rng = np.random.RandomState(seed)

        # Simulator state
        self.current_time = 0.0
        self.event_queue: List[Event] = []
        self._event_counter = 0

        # Physical link state
        self.packet_queue: Deque[Packet] = deque()
        self.channel_busy = False
        self.current_transmitting_packet: Optional[Packet] = None

        # Statistics and tracking
        self.all_generated_packets: List[Packet] = []
        self.dropped_packets: List[Packet] = []
        self.queue_history: List[tuple[float, int, int]] = []  # (t, count, bytes)
        self.receiver = Receiver()

    def get_network_state(self) -> NetworkState:
        """Returns instantaneous network state for strategy policy decisions."""
        q_len = len(self.packet_queue)
        q_bytes = sum(p.total_bytes for p in self.packet_queue)
        bps = self.bandwidth_kbps * 1000.0
        est_q_delay = (q_bytes * 8.0) / bps if bps > 0 else 0.0
        nominal_tx_time = (128 * 8.0) / bps if bps > 0 else 0.01

        return NetworkState(
            queue_len=q_len,
            queue_bytes=q_bytes,
            est_queue_delay=est_q_delay,
            est_tx_time_per_packet=nominal_tx_time,
            channel_busy=self.channel_busy,
            bandwidth_kbps=self.bandwidth_kbps,
        )

    def _schedule_event(self, timestamp: float, event_type: str, data: Any = None):
        self._event_counter += 1
        event = Event(
            timestamp=timestamp,
            priority_order=self._event_counter,
            event_type=event_type,
            data=data,
        )
        heapq.heappush(self.event_queue, event)

    def _enqueue_packet(self, packet: Packet):
        """Places a packet into the link FIFO queue or transmits immediately if channel idle."""
        self.all_generated_packets.append(packet)

        if len(self.packet_queue) >= self.max_queue_packets:
            packet.was_dropped = True
            packet.drop_reason = "QUEUE_OVERFLOW"
            self.dropped_packets.append(packet)
            return

        self.packet_queue.append(packet)
        self.queue_history.append((self.current_time, len(self.packet_queue), sum(p.total_bytes for p in self.packet_queue)))

        if not self.channel_busy:
            self._start_next_transmission()

    def _start_next_transmission(self):
        """Pulls head packet from FIFO queue and initiates transmission over the medium."""
        if not self.packet_queue:
            self.channel_busy = False
            self.current_transmitting_packet = None
            return

        self.channel_busy = True
        pkt = self.packet_queue.popleft()
        self.current_transmitting_packet = pkt
        self.queue_history.append((self.current_time, len(self.packet_queue), sum(p.total_bytes for p in self.packet_queue)))

        pkt.transmission_start_time = self.current_time
        tx_bits = pkt.total_bytes * 8.0
        tx_seconds = tx_bits / (self.bandwidth_kbps * 1000.0)
        completion_time = self.current_time + tx_seconds
        pkt.transmission_end_time = completion_time

        self._schedule_event(completion_time, "TX_COMPLETE", pkt)

    def run(
        self,
        strategy: BaseAggregationStrategy,
        readings_workload: List[SensorReading],
        cross_traffic_packets: List[Packet],
        duration_s: float,
        timer_interval_s: Optional[float] = None,
    ) -> Receiver:
        """
        Executes the discrete-event simulation until duration_s is reached.
        """
        # 1. Schedule all sensor readings
        for reading in readings_workload:
            if reading.timestamp <= duration_s:
                self._schedule_event(reading.timestamp, "READING_ARRIVED", reading)

        # 2. Schedule cross-traffic background arrivals
        for pkt in cross_traffic_packets:
            if pkt.creation_time <= duration_s:
                self._schedule_event(pkt.creation_time, "CROSS_TRAFFIC_ARRIVED", pkt)

        # 3. Schedule strategy timer ticks
        # For fixed batching: fires at batch interval.
        # For adaptive: fires at frequent sub-intervals (0.05s) to dynamically check deadlines/max wait.
        tick_interval = timer_interval_s or 0.05
        t_tick = tick_interval
        while t_tick <= duration_s:
            self._schedule_event(t_tick, "TIMER_TICK", None)
            t_tick += tick_interval

        # 4. Simulation event loop
        while self.event_queue:
            event = heapq.heappop(self.event_queue)
            self.current_time = event.timestamp

            if event.event_type == "READING_ARRIVED":
                reading: SensorReading = event.data
                state = self.get_network_state()
                packets = strategy.on_reading_arrived(reading, self.current_time, state)
                for pkt in packets:
                    self._enqueue_packet(pkt)

            elif event.event_type == "TIMER_TICK":
                state = self.get_network_state()
                packets = strategy.on_timer_tick(self.current_time, state)
                for pkt in packets:
                    self._enqueue_packet(pkt)

            elif event.event_type == "CROSS_TRAFFIC_ARRIVED":
                cross_pkt: Packet = event.data
                self._enqueue_packet(cross_pkt)

            elif event.event_type == "TX_COMPLETE":
                completed_pkt: Packet = event.data
                
                # Check for channel transmission loss
                if self.rng.random() < self.packet_loss_rate:
                    completed_pkt.was_dropped = True
                    completed_pkt.drop_reason = "CHANNEL_LOSS"
                    self.dropped_packets.append(completed_pkt)
                else:
                    delivery_time = self.current_time + self.propagation_delay_s
                    self.receiver.receive_packet(completed_pkt, delivery_time)

                # Channel is now free; serve next queued packet
                self._start_next_transmission()

        # 5. Simulation end: flush residual buffer from strategy
        residual_packets = strategy.flush_residual(duration_s)
        for pkt in residual_packets:
            self._enqueue_packet(pkt)

        # 6. Allow remaining queued packets to drain until link clears or limit reached
        drain_limit = duration_s + 5.0
        while (self.channel_busy or self.packet_queue or self.event_queue) and self.current_time < drain_limit:
            if not self.event_queue and self.packet_queue and not self.channel_busy:
                self._start_next_transmission()
            if not self.event_queue:
                break
            event = heapq.heappop(self.event_queue)
            self.current_time = event.timestamp
            if event.event_type == "TX_COMPLETE":
                completed_pkt: Packet = event.data
                if self.rng.random() < self.packet_loss_rate:
                    completed_pkt.was_dropped = True
                    completed_pkt.drop_reason = "CHANNEL_LOSS"
                    self.dropped_packets.append(completed_pkt)
                else:
                    delivery_time = self.current_time + self.propagation_delay_s
                    self.receiver.receive_packet(completed_pkt, delivery_time)
                self._start_next_transmission()

        # Any packet still stranded in queue after drain limit is marked dropped
        while self.packet_queue:
            stranded = self.packet_queue.popleft()
            stranded.was_dropped = True
            stranded.drop_reason = "SIMULATION_DRAIN_TIMEOUT"
            self.dropped_packets.append(stranded)

        return self.receiver
