"""
TinyFlow — Fixed-Interval Batching Strategy Deep-Dive.
Analyzes buffer occupancy, batch sizes, interval enforcement, and buffering delays.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.express as px

from tinyflow.ui_shared import apply_shared_theme, get_or_create_active_result, render_experiment_header_banner
from tinyflow.visualization.plots import create_queue_history_plot, DARK_TEMPLATE


def render_fixed_batching():
    try:
        st.set_page_config(
            page_title="TinyFlow — Fixed Batching",
            layout="wide",
        )
    except Exception:
        pass
    apply_shared_theme()

    result = get_or_create_active_result()
    cfg = result.config
    trace = result.traces["Fixed-Interval"]
    m = trace.metrics

    st.title("Strategy: Fixed-Interval Batching", anchor=False)
    st.markdown(
        f"<p style='color: #94a3b8; font-size: 1rem; margin-top: -10px; margin-bottom: 18px;'>"
        f"Periodic aggregation: holds sensor readings in buffer and flushes every <b>{cfg.fixed_batch_interval_s:.2f}s</b> "
        f"or when MTU limit ({cfg.max_packet_size}B) is reached."
        f"</p>",
        unsafe_allow_html=True,
    )

    render_experiment_header_banner(result)

    # 1. Metric Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Batch Interval", f"{cfg.fixed_batch_interval_s}s")
    with col2:
        st.metric("Avg Batch Size", f"{m.avg_batch_size:.1f} readings")
    with col3:
        st.metric("Header Overhead", f"{m.header_overhead_percent}%")
    with col4:
        st.metric("Mean Latency", f"{m.mean_e2e_delay_ms} ms")
    with col5:
        st.metric("Deadline Miss Rate", f"{m.deadline_miss_rate_percent}%")

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 2. Charts Row: Batch Sizes & Transmission Events
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Batch Size Distribution", anchor=False)
        batch_sizes = m.batch_sizes
        if batch_sizes:
            df_bs = pd.DataFrame({"Batch Size": batch_sizes})
            fig_bs = px.histogram(
                df_bs,
                x="Batch Size",
                nbins=15,
                color_discrete_sequence=["#06b6d4"],
            )
            fig_bs.update_layout(
                template=DARK_TEMPLATE,
                height=300,
                title=dict(text="Readings per Transmitted Packet", font=dict(size=14, color="#f8fafc")),
                yaxis_title="Packet Count",
            )
            st.plotly_chart(fig_bs, use_container_width=True)
        else:
            st.info("No batched packets recorded.")

    with col_right:
        st.subheader("Periodic Transmission Timeline", anchor=False)
        timeline = m.packet_timeline
        if timeline:
            df_tl = pd.DataFrame(timeline)
            fig_tl = px.scatter(
                df_tl,
                x="tx_start",
                y="readings_count",
                size="total_bytes",
                color_discrete_sequence=["#06b6d4"],
                labels={"tx_start": "Simulation Time (s)", "readings_count": "Batch Size (Readings)", "total_bytes": "Bytes"},
                hover_data=["packet_id", "seq", "total_bytes"],
            )
            fig_tl.update_layout(
                template=DARK_TEMPLATE,
                height=300,
                title=dict(text="Batch Transmission Dispatches Over Time", font=dict(size=14, color="#f8fafc")),
            )
            st.plotly_chart(fig_tl, use_container_width=True)
        else:
            st.info("No packets transmitted.")

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 3. Holding Latency & Queue Dynamics Row
    col_delays, col_q = st.columns(2)

    with col_delays:
        st.subheader("Holding & Delivery Delay Distribution", anchor=False)
        delays = [r.e2e_delay * 1000.0 for r in trace.delivered_records]
        if delays:
            fig_hist = px.histogram(
                x=delays,
                nbins=25,
                labels={"x": "Delay (ms)"},
                color_discrete_sequence=["#0891b2"],
            )
            fig_hist.update_layout(
                template=DARK_TEMPLATE,
                height=280,
                title=dict(text="End-to-End Latency Spread (ms)", font=dict(size=14, color="#f8fafc")),
                yaxis_title="Reading Count",
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("No delivered readings recorded.")

    with col_q:
        st.subheader("Channel Queue History", anchor=False)
        fig_q = create_queue_history_plot(trace.queue_history, title="Fixed Batching Queue Depth")
        st.plotly_chart(fig_q, use_container_width=True)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 4. Batched Packet Inventory Table
    st.subheader("Batched Packets Inspection Log", anchor=False)
    if timeline:
        df_pkts = pd.DataFrame([
            {
                "Packet ID": p["packet_id"],
                "Seq #": p["seq"],
                "Batch Size": f"{p['readings_count']} readings",
                "Total Bytes": f"{p['total_bytes']} B",
                "Dispatch Time": f"{p['tx_start']:.3f}s" if p["tx_start"] is not None else "N/A",
                "Completion Time": f"{p['tx_end']:.3f}s" if p["tx_end"] is not None else "N/A",
                "Status": "Delivered" if not p["was_dropped"] else f"Dropped ({p['drop_reason']})",
            }
            for p in timeline[:100]
        ])
        st.dataframe(df_pkts, use_container_width=True, hide_index=True)


render_fixed_batching()
