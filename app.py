"""
TinyFlow — Adaptive Packet Aggregation for IoT Networks.
Main Application Entry Point and Overview Dashboard.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.express as px

from tinyflow.ui_shared import apply_shared_theme, get_or_create_active_result, render_experiment_header_banner
from tinyflow.visualization.plots import (
    create_comparison_bar_chart,
    create_throughput_vs_delay_tradeoff,
    create_overhead_and_energy_comparison,
    COLOR_MAP,
)


def render_overview():
    try:
        st.set_page_config(
            page_title="TinyFlow — IoT Adaptive Aggregation",
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except Exception:
        pass

    apply_shared_theme()

    result = get_or_create_active_result()
    cfg = result.config
    metrics_map = result.metrics

    st.title("TinyFlow: Adaptive Packet Aggregation for IoT Networks", anchor=False)
    st.markdown(
        "<p style='color: #94a3b8; font-size: 1.05rem; margin-top: -10px; margin-bottom: 20px;'>"
        "Empirical investigation of dynamic packet batching, network congestion management, and deadline guarantees."
        "</p>",
        unsafe_allow_html=True,
    )

    render_experiment_header_banner(result)

    # 1. High-level metric highlights across the 3 strategies
    st.subheader("Key Strategy Performance Metrics", anchor=False)

    col1, col2, col3, col4, col5 = st.columns(5)

    imm = metrics_map["Immediate"]
    fix = metrics_map["Fixed-Interval"]
    adp = metrics_map["Adaptive"]

    with col1:
        st.metric(
            label="Adaptive Header Overhead",
            value=f"{adp.header_overhead_percent}%",
            delta=f"{adp.header_overhead_percent - imm.header_overhead_percent:.1f}% vs Imm",
            delta_color="inverse",
        )
    with col2:
        st.metric(
            label="Adaptive Mean Delay",
            value=f"{adp.mean_e2e_delay_ms} ms",
            delta=f"{adp.mean_e2e_delay_ms - fix.mean_e2e_delay_ms:.1f} ms vs Fixed",
            delta_color="inverse",
        )
    with col3:
        st.metric(
            label="Useful Throughput",
            value=f"{adp.useful_throughput_bps} B/s",
            delta=f"{adp.useful_throughput_bps - fix.useful_throughput_bps:.1f} vs Fixed",
        )
    with col4:
        st.metric(
            label="Adaptive Miss Rate",
            value=f"{adp.deadline_miss_rate_percent}%",
            delta=f"{adp.deadline_miss_rate_percent - fix.deadline_miss_rate_percent:.1f}% vs Fixed",
            delta_color="inverse",
        )
    with col5:
        st.metric(
            label="Est. Energy (mJ)",
            value=f"{adp.total_energy_estimate_mj} mJ",
            delta=f"{adp.total_energy_estimate_mj - imm.total_energy_estimate_mj:.2f} mJ vs Imm",
            delta_color="inverse",
        )

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 2. Side-by-Side Strategy Summary Table
    st.subheader("Side-by-Side Strategy Evaluation", anchor=False)
    summary_data = result.get_summary_comparison()
    df_summary = pd.DataFrame(summary_data)
    
    st.dataframe(
        df_summary,
        column_config={
            "Strategy": st.column_config.TextColumn("Strategy", width="medium"),
            "Header Overhead (%)": st.column_config.NumberColumn("Header Overhead", format="%.2f%%"),
            "Throughput (bytes/s)": st.column_config.NumberColumn("Useful Throughput (B/s)", format="%.2f"),
            "Mean Delay (ms)": st.column_config.NumberColumn("Mean E2E Delay (ms)", format="%.1f ms"),
            "P95 Delay (ms)": st.column_config.NumberColumn("95th Pct Delay (ms)", format="%.1f ms"),
            "Deadline Miss Rate (%)": st.column_config.NumberColumn("Deadline Miss Rate", format="%.2f%%"),
            "Energy Est (mJ)": st.column_config.NumberColumn("Energy Est. (mJ)", format="%.3f mJ"),
            "Avg Batch Size": st.column_config.NumberColumn("Avg Batch (readings)", format="%.2f"),
            "Delivered Readings": st.column_config.NumberColumn("Delivered", format="%d"),
            "Total Readings": st.column_config.NumberColumn("Generated", format="%d"),
        },
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 3. Visual Comparisons
    col_chart_left, col_chart_right = st.columns(2)

    with col_chart_left:
        fig_tradeoff = create_throughput_vs_delay_tradeoff(metrics_map)
        st.plotly_chart(fig_tradeoff, use_container_width=True)

    with col_chart_right:
        fig_overhead_energy = create_overhead_and_energy_comparison(metrics_map)
        st.plotly_chart(fig_overhead_energy, use_container_width=True)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 4. Objective Evaluation & Rigorous Analysis
    st.subheader("Objective-Based Evaluation & Recommendations", anchor=False)

    st.markdown(
        f"""
        <div style="background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 18px; line-height: 1.6;">
            <h4 style="margin-top: 0; color: #f8fafc; font-size: 1.05rem;">Optimization Trade-Off Analysis</h4>
            <p style="color: #cbd5e1; font-size: 0.9rem;">
                No single aggregation strategy strictly dominates across every operational dimension:
            </p>
            <ul style="color: #cbd5e1; font-size: 0.88rem;">
                <li><b>Immediate Transmission:</b> Minimizes buffering delay ({imm.mean_e2e_delay_ms:.1f} ms) by transmitting immediately upon reading arrival, but suffers from severe header overhead ({imm.header_overhead_percent:.1f}%) and highest radio energy expenditure ({imm.total_energy_estimate_mj:.2f} mJ).</li>
                <li><b>Fixed-Interval Batching ({cfg.fixed_batch_interval_s}s):</b> Drastically reduces header overhead down to {fix.header_overhead_percent:.1f}%, but incurs substantial holding latency ({fix.mean_e2e_delay_ms:.1f} ms) and suffers a deadline miss rate of {fix.deadline_miss_rate_percent:.1f}% when intervals exceed sensor urgency windows.</li>
                <li><b>Adaptive Aggregation:</b> Dynamically balances overhead ({adp.header_overhead_percent:.1f}%) against delivery deadlines ({adp.deadline_miss_rate_percent:.1f}% miss rate). By evaluating buffer capacity, network queue delay, and reading slack, it preserves urgency without incurring excessive header waste.</li>
            </ul>
            <div style="margin-top: 12px; padding: 10px 14px; background-color: #0f172a; border-left: 4px solid #10b981; border-radius: 3px;">
                <span style="font-size: 0.85rem; color: #94a3b8; font-weight: 600;">BEST-FIT RECOMMENDATION:</span>
                <span style="font-size: 0.88rem; color: #e2e8f0; margin-left: 6px;">
                    When deadline compliance under link contention is paramount, <b>Adaptive Aggregation</b> provides the optimal Pareto trade-off between energy/header reduction and latency guarantees.
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Configure multipage navigation
nav = st.navigation([
    st.Page(render_overview, title="Overview", default=True),
    st.Page("pages/1_Immediate_Strategy.py", title="Immediate Strategy"),
    st.Page("pages/2_Fixed_Batching.py", title="Fixed Batching"),
    st.Page("pages/3_Adaptive_Strategy.py", title="Adaptive Strategy"),
    st.Page("pages/4_Strategy_Comparison.py", title="Strategy Comparison"),
    st.Page("pages/5_Experiment_Setup.py", title="Experiment Setup"),
])

if __name__ == "__main__":
    nav.run()
