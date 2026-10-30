"""
Shared UI state, navigation helpers, styling, and session management for Streamlit pages.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from typing import Optional

from tinyflow.database.storage import get_saved_experiment, list_saved_experiments, save_experiment_result
from tinyflow.experiment.config import ExperimentConfig
from tinyflow.experiment.runner import ExperimentRunner, ExperimentRunResult
from tinyflow.network.cross_traffic import CongestionPreset


CUSTOM_CSS = """
<style>
/* Clean typography & neutral background palette */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

code, pre, .stCodeBlock {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Metric card styling: clean border, subtle background, no decorative neon */
div[data-testid="stMetric"] {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 12px 16px;
}

div[data-testid="stMetricLabel"] {
    font-size: 0.82rem;
    font-weight: 500;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

div[data-testid="stMetricValue"] {
    font-size: 1.45rem;
    font-weight: 600;
    color: #f8fafc;
}

/* Table styling */
.dataframe {
    font-size: 0.85rem !important;
    border: 1px solid #334155 !important;
}

/* Hide Deploy button */
[data-testid="stDeployButton"],
.stDeployButton,
div[data-testid="stDeployButton"] {
    display: none !important;
    visibility: hidden !important;
}

/* Hide header anchor link / clip symbols */
[data-testid="stHeaderActionElements"],
.stHeadingAnchor,
a.header-anchor,
a[data-testid="stHeaderAnchor"],
button[data-testid="stHeaderActionButton"] {
    display: none !important;
    visibility: hidden !important;
}

/* Subheading dividers */
.section-divider {
    border-bottom: 1px solid #334155;
    margin-top: 1.2rem;
    margin-bottom: 1.2rem;
}

/* Status badge pills */
.badge-immediate {
    background-color: #78350f;
    color: #fde68a;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    border: 1px solid #b45309;
}

.badge-fixed {
    background-color: #164e63;
    color: #a5f3fc;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    border: 1px solid #0891b2;
}

.badge-adaptive {
    background-color: #064e3b;
    color: #a7f3d0;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    border: 1px solid #059669;
}

/* Decision reason badge */
.badge-reason {
    background-color: #1e293b;
    color: #cbd5e1;
    padding: 3px 6px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-family: 'JetBrains Mono', monospace;
    border: 1px solid #475569;
}
</style>
"""


def apply_shared_theme():
    """Injects custom CSS for consistent typography and contrast."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def get_or_create_active_result() -> ExperimentRunResult:
    """
    Ensures an active simulation experiment result is always present in session_state.
    Runs baseline configuration if none exists.
    """
    if "current_result" not in st.session_state:
        # Check if saved experiments exist in SQLite
        saved_list = list_saved_experiments()
        if saved_list:
            first_id = saved_list[0]["id"]
            # We can re-run with loaded config to rehydrate in-memory traces
            saved = get_saved_experiment(first_id)
            if saved and "config" in saved:
                cfg = ExperimentConfig.from_dict(saved["config"])
                res = ExperimentRunner.run_experiment(cfg)
                res.experiment_id = first_id
                st.session_state["current_result"] = res
                return res

        # Run fresh default baseline experiment
        baseline_cfg = ExperimentConfig(
            num_sensors=5,
            reading_rate_hz=1.0,
            baseline_deadline_s=2.0,
            duration_s=20.0,
            bandwidth_kbps=100.0,
            packet_loss_rate=0.02,
            congestion_preset=CongestionPreset.LOW,
            fixed_batch_interval_s=1.0,
            max_packet_size=128,
            seed=42,
            name="Baseline 5-Sensor Monitoring Experiment",
        )
        res = ExperimentRunner.run_experiment(baseline_cfg)
        save_experiment_result(res)
        st.session_state["current_result"] = res

    return st.session_state["current_result"]


def render_experiment_header_banner(result: ExperimentRunResult):
    """Displays active experiment metadata bar with crisp styling."""
    cfg = result.config
    st.markdown(
        f"""
        <div style="background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 10px 16px; margin-bottom: 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <div>
                <span style="font-weight: 600; color: #f8fafc; font-size: 0.95rem;">{cfg.name}</span>
                <span style="color: #64748b; font-size: 0.8rem; margin-left: 8px;">ID: {result.experiment_id}</span>
            </div>
            <div style="font-size: 0.8rem; color: #94a3b8; display: flex; gap: 14px; flex-wrap: wrap;">
                <span>Sensors: <b style="color: #f1f5f9;">{cfg.num_sensors}</b></span>
                <span>Rate: <b style="color: #f1f5f9;">{cfg.reading_rate_hz} Hz</b></span>
                <span>Bandwidth: <b style="color: #f1f5f9;">{cfg.bandwidth_kbps} kbps</b></span>
                <span>Congestion: <b style="color: #f1f5f9;">{cfg.congestion_preset.value.title()}</b></span>
                <span>Seed: <b style="color: #f1f5f9;">{cfg.seed}</b></span>
                <span>Duration: <b style="color: #f1f5f9;">{cfg.duration_s}s</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
