"""
TinyFlow — Immediate Transmission Strategy Deep-Dive.
Analyzes packet flow, queueing behavior, latency distributions, and header overhead.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from tinyflow.ui_shared import apply_shared_theme, get_or_create_active_result, render_experiment_header_banner
from tinyflow.visualization.plots import create_queue_history_plot, DARK_TEMPLATE


def render_immediate_strategy():
    try:
        st.set_page_config(
            page_title="TinyFlow — Immediate Strategy",
            layout="wide",
        )
    except Exception:
        pass
    apply_shared_theme()

    result = get_or_create_active_result()
    trace = result.traces["Immediate"]
    m = trace.metrics

    st.title("Strategy: Immediate Transmission", anchor=False)
    st.markdown(
        "<p style='color: #94a3b8; font-size: 1rem; margin-top: -10px; margin-bottom: 18px;'>"
        "Zero-buffering baseline: encapsulates every sensor reading into its own packet immediately upon arrival."
        "</p>",
        unsafe_allow_html=True,
    )

    render_experiment_header_banner(result)

    # 1. Metric Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Transmitted Packets", f"{m.total_transmitted_packets}")
    with col2:
        st.metric("Header Overhead", f"{m.header_overhead_percent}%")
    with col3:
        st.metric("Mean Latency", f"{m.mean_e2e_delay_ms} ms")
    with col4:
        st.metric("P95 Latency", f"{m.p95_e2e_delay_ms} ms")
    with col5:
        st.metric("Total Energy Est.", f"{m.total_energy_estimate_mj:.2f} mJ")

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 2. Charts Row: Transmission Flow & Queue Depth
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Packet Transmission Timeline", anchor=False)
        timeline = m.packet_timeline
        if timeline:
            df_tl = pd.DataFrame(timeline)
            fig_tl = px.scatter(
                df_tl,
                x="tx_start",
                y="total_bytes",
                color="was_dropped",
                color_discrete_map={False: "#f59e0b", True: "#ef4444"},
                labels={"tx_start": "Simulation Time (s)", "total_bytes": "Packet Size (Bytes)", "was_dropped": "Dropped"},
                hover_data=["packet_id", "seq", "tx_end", "readings_count"],
            )
            fig_tl.update_layout(
                template=DARK_TEMPLATE,
                height=300,
                title=dict(text="Packet Dispatch Timeline", font=dict(size=14, color="#f8fafc")),
            )
            st.plotly_chart(fig_tl, use_container_width=True)
        else:
            st.info("No packets transmitted.")

    with col_right:
        st.subheader("Channel Queue Behavior", anchor=False)
        fig_q = create_queue_history_plot(trace.queue_history, title="Immediate Strategy Queue Depth")
        st.plotly_chart(fig_q, use_container_width=True)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 3. Delay & Overhead Analysis Row
    col_delays, col_overhead = st.columns(2)

    with col_delays:
        st.subheader("End-to-End Delay Distribution", anchor=False)
        delays = [r.e2e_delay * 1000.0 for r in trace.delivered_records]
        if delays:
            fig_hist = px.histogram(
                x=delays,
                nbins=25,
                labels={"x": "Delay (ms)"},
                color_discrete_sequence=["#f59e0b"],
            )
            fig_hist.update_layout(
                template=DARK_TEMPLATE,
                height=280,
                title=dict(text="Distribution of Reading Delays (ms)", font=dict(size=14, color="#f8fafc")),
                yaxis_title="Reading Count",
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("No delivered readings recorded.")

    with col_overhead:
        st.subheader("Wire Byte Composition", anchor=False)
        byte_data = pd.DataFrame([
            {"Category": "Header Bytes", "Bytes": m.total_header_bytes_transmitted},
            {"Category": "Payload Bytes", "Bytes": m.total_payload_bytes_transmitted},
        ])
        fig_pie = px.pie(
            byte_data,
            names="Category",
            values="Bytes",
            hole=0.45,
            color="Category",
            color_discrete_map={"Header Bytes": "#f43f5e", "Payload Bytes": "#f59e0b"},
        )
        fig_pie.update_layout(
            template=DARK_TEMPLATE,
            height=280,
            title=dict(text=f"Header Overhead: {m.header_overhead_percent}%", font=dict(size=14, color="#f8fafc")),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 4. Detailed Reading Arrivals Log
    st.subheader("Delivered Readings Trace (Sample)", anchor=False)
    recs = trace.delivered_records[:100]
    if recs:
        df_recs = pd.DataFrame([
            {
                "Reading ID": r.reading_id,
                "Sensor": f"Sensor #{r.sensor_id}",
                "Type": r.reading_type.title(),
                "Value": f"{r.value} {r.unit}",
                "Priority": r.priority,
                "Gen Time": f"{r.generation_time:.3f}s",
                "Delivery Time": f"{r.delivery_time:.3f}s",
                "E2E Delay": f"{r.e2e_delay * 1000.0:.1f} ms",
                "Met Deadline": "Yes" if r.met_deadline else "NO (Missed)",
                "Packet ID": r.packet_id,
            }
            for r in recs
        ])
        st.dataframe(df_recs, use_container_width=True, hide_index=True)


render_immediate_strategy()
