# TinyFlow: Adaptive Packet Aggregation for IoT Networks

**TinyFlow** is a research-grade simulation framework and interactive multipage dashboard evaluating adaptive packet aggregation across constrained Internet of Things (IoT) wireless links (e.g., IEEE 802.15.4, 6LoWPAN, BLE Mesh).

---

## 1. Project Objective & Problem Statement

IoT sensor nodes continuously generate small physical telemetry samples (temperature, humidity, soil moisture). Transmitting each sample individually introduces repeated packet-header overhead (MAC layer, IP/6LoWPAN, UDP headers: typically 28+ bytes per packet) relative to a payload of only 12–16 bytes. This leads to:
1. High channel contention and frequent collisions in dense deployments.
2. Premature battery exhaustion due to RF transceiver wake-up and preamble transmission costs.
3. Wasteful bandwidth consumption on low-bitrate links (20–250 kbps).

**TinyFlow** rigorously models, benchmarks, and compares three strategies under strictly identical workloads and channel conditions:
1. **Immediate Transmission:** Flushes every reading immediately upon arrival (zero buffering delay, maximum overhead).
2. **Fixed-Interval Batching:** Buffers readings and transmits accumulated batches at a fixed interval (e.g., 1.0s) or upon MTU capacity.
3. **Adaptive Aggregation:** Evaluates buffer occupancy, network queue congestion, reading urgency/priority, oldest reading age, and remaining delivery slack to make state-driven `TRANSMIT` vs `WAIT` decisions.

---

## 2. Architecture & Modular Structure

The codebase is organized into modular layers:

```
TinyFlow/
├── app.py                          # Streamlit application entry point & Overview dashboard
├── pages/
│   ├── 1_Immediate_Strategy.py     # Packet timeline, queue depth, latency distribution
│   ├── 2_Fixed_Batching.py         # Batch size histograms, interval enforcement, holding latency
│   ├── 3_Adaptive_Strategy.py      # Real-time state monitor, genuine decision explanation audit
│   ├── 4_Strategy_Comparison.py    # Side-by-side tables, Plotly trade-off curves, multi-seed tests
│   └── 5_Experiment_Setup.py       # Validated parameter studio, SQLite history, CSV exports
├── tinyflow/
│   ├── models.py                   # SensorReading, Packet, ReadingPriority, DecisionRecord
│   ├── sensor.py                   # VirtualSensor, SensorNetworkGenerator (temperature, humidity, moisture)
│   ├── strategies/
│   │   ├── base.py                 # BaseAggregationStrategy
│   │   ├── immediate.py            # ImmediateStrategy
│   │   ├── fixed.py                # FixedIntervalBatchingStrategy
│   │   └── adaptive.py             # AdaptiveAggregationStrategy (transparent decision policy)
│   ├── network/
│   │   ├── simulator.py            # DiscreteEventSimulator, Event queue, FIFO channel
│   │   ├── cross_traffic.py        # Competing background traffic generator & congestion presets
│   │   └── receiver.py             # Receiver, packet decapsulation, duplicate and deadline validation
│   ├── metrics/
│   │   ├── calculator.py           # StrategyMetrics calculator with explicit formulas
│   │   └── energy_model.py         # Analytical RF & MCU energy estimation model
│   ├── experiment/
│   │   ├── config.py               # ExperimentConfig dataclass & parameter validation
│   │   └── runner.py               # ExperimentRunner (fair multi-strategy execution)
│   ├── database/
│   │   └── storage.py              # SQLite storage schema, queries, and CSV exporters
│   ├── visualization/
│   │   └── plots.py                # Plotly chart builders with clean technical dark theme
│   └── ui_shared.py                # Streamlit session state, navigation badges, and theme CSS
├── tests/
│   ├── test_sensor.py              # Sensor generation, priorities, deadlines, seeds
│   ├── test_packet_models.py       # Packet serialization, framing, MTU enforcement
│   ├── test_strategies.py          # Immediate and Fixed batching mechanics
│   ├── test_adaptive_logic.py      # Adaptive decision triggers and explanations
│   ├── test_network_simulator.py   # Bandwidth delay, FIFO queues, packet loss
│   ├── test_metrics.py             # Overhead, throughput, delay, energy model formulas
│   ├── test_persistence.py         # SQLite persistence and CSV export
│   ├── test_reproducibility.py     # Bitwise reproducible runs across identical seeds
│   └── test_edge_cases.py          # Residual flushes, empty buffers, severe congestion
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## 3. Adaptive Aggregation Algorithm

Unlike fixed timers or heuristic labels, TinyFlow's **Adaptive Aggregator** evaluates a multi-variable policy engine on every reading arrival and scheduled check tick.

### Decision Rules (Evaluated in Strict Priority Order)

1. **Urgent Priority Trigger (`URGENT_PRIORITY_TRIGGER`):**
   $$\exists r \in \text{Buffer} \quad \text{such that} \quad r.\text{priority} \in \{\text{HIGH}, \text{CRITICAL}\}$$
   *Action:* `TRANSMIT`. Bypasses buffering to guarantee near-zero latency for emergency events or anomaly alarms.
2. **Buffer MTU Capacity Trigger (`BUFFER_FULL_MTU`):**
   $$B_{\text{header}} + \sum_{r \in \text{Buffer}} (r.\text{payload} + B_{\text{framing}}) + \text{wire\_cost}_{\text{next}} > \text{MTU}$$
   *Action:* `TRANSMIT`. Flushes the full batch to maximize packet-header efficiency without fragmentation.
3. **Delivery Slack Safety Trigger (`DEADLINE_APPROACHING`):**
   $$\text{slack}_{\text{effective}} = \min_{r \in \text{Buffer}} (r.\text{deadline} - t_{\text{now}}) - (\Delta t_{\text{queue\_est}} + \Delta t_{\text{tx\_est}}) \le \theta_{\text{safety\_slack}}$$
   *Action:* `TRANSMIT`. Ensures accumulated readings are dispatched before downlink queue backlog causes deadline violations.
4. **Dynamic Maximum Wait Trigger (`MAX_WAIT_EXCEEDED`):**
   $$t_{\text{now}} - r_{\text{oldest}}.\text{timestamp} \ge T_{\text{max\_wait}} \times \alpha_{\text{congestion\_scale}}$$
   *Action:* `TRANSMIT`. Limits holding time for non-urgent readings; bounds maximum queuing delay.
5. **Congestion Backlog Flush (`CONGESTION_FLUSH`):**
   $$N_{\text{queue}} \ge \theta_{\text{queue\_backlog}} \quad \text{and} \quad |\text{Buffer}| \ge 3$$
   *Action:* `TRANSMIT`. Ingests aggregated readings into the link queue before downstream queue latency spikes.
6. **Aggregating Hold (`BUFFER_ROOM_WAITING`):**
   *Action:* `WAIT`. Buffer has available MTU capacity and all readings possess ample deadline slack.

Every decision records its exact triggering condition, timestamp, buffer count, buffer bytes, oldest age, and minimum slack.

---

## 4. Network Simulator & Physical Modeling

The discrete-event simulator uses a priority event queue (`heapq`) to model:
- **Bandwidth & Transmission Time:**
  $$\Delta t_{\text{tx}} = \frac{\text{Packet Size (Bytes)} \times 8}{\text{Bandwidth (bps)}}$$
- **Propagation Delay:** Configurable physical propagation latency (default: 5 ms).
- **FIFO Packet Queue:** Finite buffer with drop-tail overflow drops (`QUEUE_OVERFLOW`).
- **Channel Packet Loss:** Independent channel drop model evaluated per packet with reproducible pseudorandom seeds (`CHANNEL_LOSS`).
- **Competing Background Traffic:** Poisson arrival process ($\lambda_{\text{cross}}$) generating realistic link contention across predefined congestion presets:
  - *None:* 0 pkts/s background load.
  - *Low:* 5 pkts/s background load.
  - *Moderate:* 15 pkts/s background load.
  - *High:* 30 pkts/s background load (induces heavy link queue buildup).
- **Fairness Guarantee:** All three aggregation strategies receive the exact same generated sensor readings workload, the exact same cross-traffic schedule, and identical channel loss seeds.

---

## 5. Metrics & Mathematical Formulations

1. **Header Overhead (%):**
   $$\text{Overhead} = \frac{\sum_{p \in \text{Tx Packets}} p.\text{header\_bytes}}{\sum_{p \in \text{Tx Packets}} p.\text{total\_bytes}} \times 100\%$$
2. **Useful Throughput (Bytes/s & kbps):**
   $$\text{Throughput}_{\text{useful}} = \frac{\sum_{r \in \text{Delivered}} r.\text{payload\_bytes}}{\text{Simulation Duration (seconds)}}$$
3. **End-to-End Latency (ms):**
   $$\tau_i = (t_{\text{delivered}, i} - t_{\text{generated}, i}) \times 1000$$
   Tracks Mean, Median, 95th Percentile, Minimum, and Maximum.
4. **Deadline Miss Rate (%):**
   $$\text{Miss Rate} = \frac{N_{\text{late\_delivered}} + N_{\text{lost\_or\_dropped}}}{N_{\text{total\_generated}}} \times 100\%$$
5. **Analytical Energy Estimation Model (mJ):**
   $$E_{\text{total}} = N_{\text{pkts}} \cdot (E_{\text{tx\_startup}} + E_{\text{batch\_pack}}) + B_{\text{total\_bytes}} \cdot E_{\text{tx\_byte}} + N_{\text{readings}} \cdot E_{\text{proc\_reading}}$$
   - $E_{\text{tx\_startup}} = 0.050 \text{ mJ}$ (Radio wake-up, PLL lock, preamble transmission)
   - $E_{\text{tx\_byte}} = 0.0012 \text{ mJ/Byte}$ (Active RF transmission at 0 dBm)
   - $E_{\text{proc\_reading}} = 0.0004 \text{ mJ/Reading}$ (MCU ADC conversion and sampling)
   - $E_{\text{batch\_pack}} = 0.0008 \text{ mJ/Packet}$ (Framing and memory packing)
   *Note: Labeled strictly as an analytical model based on CC2420 / nRF52840 hardware profiles, not direct hardware measurement.*

---

## 6. Installation & Execution

### Prerequisites
- Python 3.10+ (Tested on Python 3.13)
- Dependencies: `streamlit`, `plotly`, `numpy`, `pandas`, `pytest`

### Setup
```bash
# Clone and enter the repository
cd TinyFlow

# Install dependencies
pip install -r requirements.txt
```

### Run Automated Tests
```bash
python -m pytest
```
*Result: 23 passing tests covering models, strategies, adaptive logic, simulator, metrics, persistence, and reproducibility.*

### Launch the Streamlit Dashboard
```bash
python -m streamlit run app.py
```
Open your browser to `http://localhost:8501`.

---

## 7. Multipage Dashboard Navigation

- **Overview (`app.py` / `1_Overview.py`):** Selected experiment configuration, 5-metric high-level cards, side-by-side strategy table, throughput vs delay trade-off curve, and objective-based evaluation.
- **Immediate Strategy (`2_Immediate_Strategy.py`):** Individual packet flow, queue dynamics, delay histogram, and wire byte composition.
- **Fixed Batching (`3_Fixed_Batching.py`):** Batch size distribution, dispatch timeline, interval compliance, and holding delays.
- **Adaptive Strategy (`4_Adaptive_Strategy.py`):** Live algorithm state monitor, real-time numeric decision reason audit, trigger breakdown donut chart, buffer timeline, and filterable decision history.
- **Strategy Comparison (`5_Strategy_Comparison.py`):** Side-by-side metric tables, Plotly charts for overhead, throughput, latency spread, deadline misses, and multi-seed variability tests (Mean ± Std Dev).
- **Experiment Setup (`6_Experiment_Setup.py`):** Configurable sliders for sensors, rates, bandwidth, loss, and congestion presets; SQLite persistence library; and CSV export.

---

## 8. Limitations & Assumptions

1. **Analytical Radio Model:** Energy consumption is modeled analytically based on datasheet power states (wake-up + per-byte active power + MCU sampling), rather than physical oscilloscope current shunt measurements.
2. **Single-Hop Bottleneck:** The simulator models a shared star-topology link (sensors $\to$ gateway/sink). Multi-hop RPL routing mesh dynamics are abstracted into the shared queue and cross-traffic contention generator.
3. **Static MTU:** Default MTU is 128 bytes (IEEE 802.15.4 standard frame limit). Larger MTUs (up to 1500 bytes) can be selected in the setup studio.
