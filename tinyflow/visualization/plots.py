"""
Plotly visualization builders for TinyFlow dashboard.
Implements a clean, technical theme with high readability and purposeful color palettes.
"""

from __future__ import annotations
from typing import Dict, List, Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from tinyflow.metrics.calculator import StrategyMetrics
from tinyflow.models import DecisionRecord

# Cohesive, high-contrast strategy color palette
COLOR_MAP = {
    "Immediate": "#f59e0b",       # Amber
    "Fixed-Interval": "#06b6d4",  # Cyan
    "Adaptive": "#10b981",        # Emerald
    "cross_traffic": "#64748b",   # Slate
}

DARK_TEMPLATE = {
    "layout": {
        "paper_bgcolor": "rgba(15, 23, 42, 0.0)",  # Transparent / Slate-900
        "plot_bgcolor": "rgba(30, 41, 59, 0.4)",   # Slate-800 translucent
        "font": {"color": "#e2e8f0", "family": "Inter, system-ui, sans-serif"},
        "xaxis": {
            "gridcolor": "#334155",
            "zerolinecolor": "#475569",
            "showline": True,
            "linecolor": "#475569",
        },
        "yaxis": {
            "gridcolor": "#334155",
            "zerolinecolor": "#475569",
            "showline": True,
            "linecolor": "#475569",
        },
        "margin": {"l": 50, "r": 30, "t": 50, "b": 45},
    }
}


def create_comparison_bar_chart(
    metrics_map: Dict[str, StrategyMetrics],
    metric_attr: str,
    title: str,
    yaxis_title: str,
    unit_suffix: str = "",
) -> go.Figure:
    """Creates a stylized bar chart comparing the three strategies on a single metric."""
    strategies = list(metrics_map.keys())
    values = [getattr(m, metric_attr) for m in metrics_map.values()]
    colors = [COLOR_MAP.get(s, "#3b82f6") for s in strategies]

    fig = go.Figure(
        data=[
            go.Bar(
                x=strategies,
                y=values,
                marker=dict(color=colors, line=dict(color="#ffffff", width=1)),
                text=[f"{v} {unit_suffix}".strip() for v in values],
                textposition="auto",
            )
        ]
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color="#f8fafc")),
        yaxis_title=yaxis_title,
        xaxis_title="Strategy",
        template=DARK_TEMPLATE,
        height=320,
    )
    return fig


def create_throughput_vs_delay_tradeoff(
    metrics_map: Dict[str, StrategyMetrics]
) -> go.Figure:
    """Trade-off scatter plot: Useful Throughput vs Mean End-to-End Latency."""
    fig = go.Figure()
    for name, m in metrics_map.items():
        color = COLOR_MAP.get(name, "#3b82f6")
        fig.add_trace(
            go.Scatter(
                x=[m.mean_e2e_delay_ms],
                y=[m.useful_throughput_kbps],
                mode="markers+text",
                marker=dict(size=22, color=color, line=dict(color="#ffffff", width=2)),
                text=[name],
                textposition="top center",
                name=name,
                hovertemplate=(
                    f"<b>{name}</b><br>"
                    f"Throughput: {m.useful_throughput_kbps} kbps<br>"
                    f"Mean Delay: {m.mean_e2e_delay_ms} ms<br>"
                    f"P95 Delay: {m.p95_e2e_delay_ms} ms<br>"
                    f"Overhead: {m.header_overhead_percent}%<br>"
                    f"Avg Batch: {m.avg_batch_size}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=dict(text="Efficiency vs Latency Trade-Off Space", font=dict(size=15, color="#f8fafc")),
        xaxis_title="Mean End-to-End Delay (ms)",
        yaxis_title="Useful Throughput (kbps)",
        template=DARK_TEMPLATE,
        height=380,
        showlegend=False,
    )
    return fig


def create_overhead_and_energy_comparison(
    metrics_map: Dict[str, StrategyMetrics]
) -> go.Figure:
    """Grouped chart comparing Header Overhead (%) and Estimated Energy (mJ)."""
    strategies = list(metrics_map.keys())
    overhead_vals = [m.header_overhead_percent for m in metrics_map.values()]
    energy_vals = [m.total_energy_estimate_mj for m in metrics_map.values()]

    fig = go.Figure(
        data=[
            go.Bar(
                name="Header Overhead (%)",
                x=strategies,
                y=overhead_vals,
                marker_color="#f43f5e",
                text=[f"{v}%" for v in overhead_vals],
                textposition="auto",
            ),
            go.Bar(
                name="Estimated Energy (mJ)",
                x=strategies,
                y=energy_vals,
                marker_color="#3b82f6",
                text=[f"{v} mJ" for v in energy_vals],
                textposition="auto",
            ),
        ]
    )
    fig.update_layout(
        title=dict(text="Header Overhead (%) & Estimated Energy (mJ)", font=dict(size=15, color="#f8fafc")),
        barmode="group",
        template=DARK_TEMPLATE,
        height=340,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def create_delay_distribution_boxplot(
    traces_map: Dict[str, Any]
) -> go.Figure:
    """Boxplot of end-to-end reading delivery latency across strategies."""
    fig = go.Figure()
    for name, trace in traces_map.items():
        recs = trace.delivered_records
        delays_ms = [r.e2e_delay * 1000.0 for r in recs]
        if delays_ms:
            fig.add_trace(
                go.Box(
                    y=delays_ms,
                    name=name,
                    marker_color=COLOR_MAP.get(name, "#3b82f6"),
                    boxpoints="outliers",
                )
            )

    fig.update_layout(
        title=dict(text="End-to-End Latency Distribution (ms)", font=dict(size=15, color="#f8fafc")),
        yaxis_title="Delay (ms)",
        template=DARK_TEMPLATE,
        height=340,
    )
    return fig


def create_queue_history_plot(
    queue_history: List[tuple[float, int, int]],
    title: str = "Link Queue Occupancy Over Time"
) -> go.Figure:
    """Plots queue depth over the simulation timeline."""
    if not queue_history:
        fig = go.Figure()
        fig.update_layout(title=title, template=DARK_TEMPLATE)
        return fig

    times = [entry[0] for entry in queue_history]
    counts = [entry[1] for entry in queue_history]

    fig = go.Figure(
        data=[
            go.Scatter(
                x=times,
                y=counts,
                mode="lines",
                line=dict(color="#38bdf8", width=2),
                fill="tozeroy",
                fillcolor="rgba(56, 189, 248, 0.15)",
                name="Queued Packets",
            )
        ]
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color="#f8fafc")),
        xaxis_title="Simulation Time (s)",
        yaxis_title="Packets in Queue",
        template=DARK_TEMPLATE,
        height=280,
    )
    return fig


def create_adaptive_reasons_chart(
    decisions: List[DecisionRecord]
) -> go.Figure:
    """Donut chart showing breakdown of triggering conditions for Adaptive decisions."""
    if not decisions:
        fig = go.Figure()
        fig.update_layout(title="Decision Triggers Breakdown", template=DARK_TEMPLATE)
        return fig

    # Filter to TRANSMIT decisions to see why packets were flushed
    tx_decisions = [d for d in decisions if d.action.value == "TRANSMIT"]
    target = tx_decisions if tx_decisions else decisions

    df = pd.DataFrame([{"reason": d.reason_code.value} for d in target])
    counts = df["reason"].value_counts().reset_index()
    counts.columns = ["reason", "count"]

    fig = px.pie(
        counts,
        names="reason",
        values="count",
        hole=0.45,
        color_discrete_sequence=["#10b981", "#3b82f6", "#f59e0b", "#ec4899", "#8b5cf6"],
    )
    fig.update_layout(
        title=dict(text="Adaptive Trigger Reasons Breakdown", font=dict(size=15, color="#f8fafc")),
        template=DARK_TEMPLATE,
        height=320,
        legend=dict(orientation="v", yanchor="middle", y=0.5),
    )
    return fig


def create_buffer_occupancy_timeline(
    decisions: List[DecisionRecord]
) -> go.Figure:
    """Plots buffer occupancy and transmit events over time."""
    if not decisions:
        fig = go.Figure()
        fig.update_layout(title="Buffer State Timeline", template=DARK_TEMPLATE)
        return fig

    times = [d.timestamp for d in decisions]
    counts = [d.buffer_count for d in decisions]
    actions = [d.action.value for d in decisions]

    tx_times = [d.timestamp for d in decisions if d.action.value == "TRANSMIT"]
    tx_counts = [d.buffer_count for d in decisions if d.action.value == "TRANSMIT"]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=times,
            y=counts,
            mode="lines",
            line=dict(color="#64748b", width=1.5),
            name="Buffered Readings",
        )
    )
    if tx_times:
        fig.add_trace(
            go.Scatter(
                x=tx_times,
                y=tx_counts,
                mode="markers",
                marker=dict(size=9, color="#10b981", symbol="circle"),
                name="Transmit Event",
            )
        )

    fig.update_layout(
        title=dict(text="Adaptive Buffer Occupancy & Transmit Events", font=dict(size=15, color="#f8fafc")),
        xaxis_title="Simulation Time (s)",
        yaxis_title="Readings in Buffer",
        template=DARK_TEMPLATE,
        height=300,
    )
    return fig
