"""
TinyFlow — Comparative Strategy Evaluation.
Side-by-side metric tables, interactive visualizations, and parametric comparisons.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from tinyflow.experiment.runner import ExperimentRunner
from tinyflow.ui_shared import apply_shared_theme, get_or_create_active_result, render_experiment_header_banner
from tinyflow.visualization.plots import (
    create_comparison_bar_chart,
    create_delay_distribution_boxplot,
    create_overhead_and_energy_comparison,
    create_throughput_vs_delay_tradeoff,
    COLOR_MAP,
    DARK_TEMPLATE,
)


def render_strategy_comparison():
    try:
        st.set_page_config(
            page_title="TinyFlow — Strategy Comparison",
            layout="wide",
        )
    except Exception:
        pass
    apply_shared_theme()

    result = get_or_create_active_result()
    cfg = result.config
    metrics_map = result.metrics

    st.title("Comparative Performance Evaluation", anchor=False)
    st.markdown(
        "<p style='color: #94a3b8; font-size: 1rem; margin-top: -10px; margin-bottom: 18px;'>"
        "Direct side-by-side evaluation of Immediate, Fixed-Interval, and Adaptive strategies under strictly identical workloads."
        "</p>",
        unsafe_allow_html=True,
    )

    render_experiment_header_banner(result)

    # 1. Full Results Table with Clear Units
    st.subheader("Performance Metrics Summary Table", anchor=False)
    summary_data = result.get_summary_comparison()
    df_summary = pd.DataFrame(summary_data)

    st.dataframe(
        df_summary,
        column_config={
            "Strategy": st.column_config.TextColumn("Strategy Name", width="medium"),
            "Header Overhead (%)": st.column_config.NumberColumn("Header Overhead", format="%.2f%%"),
            "Throughput (bytes/s)": st.column_config.NumberColumn("Useful Throughput", format="%.2f B/s"),
            "Mean Delay (ms)": st.column_config.NumberColumn("Mean Delay", format="%.1f ms"),
            "P95 Delay (ms)": st.column_config.NumberColumn("95th Pct Delay", format="%.1f ms"),
            "Deadline Miss Rate (%)": st.column_config.NumberColumn("Miss Rate", format="%.2f%%"),
            "Energy Est (mJ)": st.column_config.NumberColumn("Est. Energy", format="%.3f mJ"),
            "Avg Batch Size": st.column_config.NumberColumn("Avg Batch", format="%.2f"),
            "Delivered Readings": st.column_config.NumberColumn("Delivered", format="%d"),
            "Total Readings": st.column_config.NumberColumn("Generated", format="%d"),
        },
        use_container_width=True,
        hide_index=True,
    )

    # Download CSV button
    csv_bytes = df_summary.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Metrics Comparison (CSV)",
        data=csv_bytes,
        file_name=f"tinyflow_comparison_{result.experiment_id}.csv",
        mime="text/csv",
    )

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 2. Key Interactive Comparison Charts
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        fig_overhead = create_comparison_bar_chart(
            metrics_map,
            metric_attr="header_overhead_percent",
            title="Header Overhead Ratio (%)",
            yaxis_title="Overhead (%)",
            unit_suffix="%",
        )
        st.plotly_chart(fig_overhead, use_container_width=True)

    with col_c2:
        fig_tp = create_comparison_bar_chart(
            metrics_map,
            metric_attr="useful_throughput_bps",
            title="Useful Throughput (Bytes / Second)",
            yaxis_title="Throughput (Bytes/s)",
            unit_suffix="B/s",
        )
        st.plotly_chart(fig_tp, use_container_width=True)

    col_c3, col_c4 = st.columns(2)

    with col_c3:
        # Grouped bar for Mean and P95 Latency
        strats = list(metrics_map.keys())
        mean_delays = [m.mean_e2e_delay_ms for m in metrics_map.values()]
        p95_delays = [m.p95_e2e_delay_ms for m in metrics_map.values()]
        fig_delay_bar = go.Figure(
            data=[
                go.Bar(name="Mean Latency (ms)", x=strats, y=mean_delays, marker_color="#38bdf8"),
                go.Bar(name="P95 Latency (ms)", x=strats, y=p95_delays, marker_color="#818cf8"),
            ]
        )
        fig_delay_bar.update_layout(
            title=dict(text="Mean & 95th Percentile Delay (ms)", font=dict(size=14, color="#f8fafc")),
            barmode="group",
            template=DARK_TEMPLATE,
            height=320,
        )
        st.plotly_chart(fig_delay_bar, use_container_width=True)

    with col_c4:
        # Deadline Miss Breakdown (Late vs Lost)
        miss_rates = [m.deadline_miss_rate_percent for m in metrics_map.values()]
        late_pcts = [m.delivered_late_percent for m in metrics_map.values()]
        lost_pcts = [m.lost_or_dropped_percent for m in metrics_map.values()]
        fig_miss = go.Figure(
            data=[
                go.Bar(name="Delivered Late (%)", x=strats, y=late_pcts, marker_color="#f59e0b"),
                go.Bar(name="Dropped / Lost (%)", x=strats, y=lost_pcts, marker_color="#ef4444"),
            ]
        )
        fig_miss.update_layout(
            title=dict(text="Deadline Miss Rate Breakdown (%)", font=dict(size=14, color="#f8fafc")),
            barmode="stack",
            template=DARK_TEMPLATE,
            height=320,
        )
        st.plotly_chart(fig_miss, use_container_width=True)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 3. Latency Distribution Boxplot
    st.subheader("Latency Variance Across Strategies", anchor=False)
    fig_box = create_delay_distribution_boxplot(result.traces)
    st.plotly_chart(fig_box, use_container_width=True)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 4. Multi-Seed Robustness Analysis
    st.subheader("Multi-Seed Variability & Robustness Analysis", anchor=False)
    st.caption("Evaluate statistical stability across 3 independent random trials (Mean ± Standard Deviation).")

    if st.button("Run 3-Seed Variability Test (Seeds 42, 43, 44)"):
        with st.spinner("Executing repeated trials under identical configurations..."):
            multi_summary = ExperimentRunner.run_multi_seed(cfg, seeds=[42, 43, 44])
            
            rows = []
            for sname, sdata in multi_summary.items():
                rows.append({
                    "Strategy": sname,
                    "Overhead (%): Mean ± Std": f"{sdata['overhead'][0]} ± {sdata['overhead'][1]}%",
                    "Mean Delay (ms): Mean ± Std": f"{sdata['delay'][0]} ± {sdata['delay'][1]} ms",
                    "Throughput (B/s): Mean ± Std": f"{sdata['throughput'][0]} ± {sdata['throughput'][1]} B/s",
                    "Miss Rate (%): Mean ± Std": f"{sdata['miss_rate'][0]} ± {sdata['miss_rate'][1]}%",
                    "Energy (mJ): Mean ± Std": f"{sdata['energy'][0]} ± {sdata['energy'][1]} mJ",
                })
            df_multi = pd.DataFrame(rows)
            st.dataframe(df_multi, use_container_width=True, hide_index=True)


render_strategy_comparison()
