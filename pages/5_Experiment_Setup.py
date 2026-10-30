"""
TinyFlow — Experiment Setup and Configuration Studio.
Configurable simulation parameters, one-click execution, persistent experiment history, and CSV export.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd

from tinyflow.database.storage import (
    delete_saved_experiment,
    export_decisions_to_csv_string,
    export_metrics_to_csv_string,
    get_saved_experiment,
    list_saved_experiments,
    save_experiment_result,
)
from tinyflow.experiment.config import ExperimentConfig
from tinyflow.experiment.runner import ExperimentRunner
from tinyflow.network.cross_traffic import CongestionPreset
from tinyflow.ui_shared import apply_shared_theme, get_or_create_active_result, render_experiment_header_banner


def render_experiment_setup():
    try:
        st.set_page_config(
            page_title="TinyFlow — Experiment Setup",
            layout="wide",
        )
    except Exception:
        pass
    apply_shared_theme()

    active_result = get_or_create_active_result()

    st.title("Experiment Setup & History Studio", anchor=False)
    st.markdown(
        "<p style='color: #94a3b8; font-size: 1rem; margin-top: -10px; margin-bottom: 18px;'>"
        "Configure virtual IoT sensors, channel bandwidth, and congestion presets. Rerun comparative simulations and manage saved experiments."
        "</p>",
        unsafe_allow_html=True,
    )

    render_experiment_header_banner(active_result)

    # 1. Configuration Form
    with st.form("experiment_config_form"):
        st.subheader("Simulation Parameters", anchor=False)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("<b style='color: #38bdf8;'>IoT Sensor Workload</b>", unsafe_allow_html=True)
            num_sensors = st.slider("Number of Sensors", min_value=1, max_value=20, value=5, step=1)
            reading_rate_hz = st.slider("Reading Rate (Hz/sensor)", min_value=0.2, max_value=10.0, value=1.0, step=0.2)
            baseline_deadline_s = st.slider("Baseline Deadline (s)", min_value=0.5, max_value=5.0, value=2.0, step=0.25)
            duration_s = st.slider("Simulation Duration (s)", min_value=5.0, max_value=60.0, value=20.0, step=5.0)

        with col2:
            st.markdown("<b style='color: #38bdf8;'>Wireless Link & Congestion</b>", unsafe_allow_html=True)
            bandwidth_kbps = st.slider("Link Bandwidth (kbps)", min_value=20.0, max_value=250.0, value=100.0, step=10.0)
            packet_loss_rate = st.slider("Channel Packet Loss Rate", min_value=0.00, max_value=0.20, value=0.02, step=0.01)
            congestion_option = st.selectbox(
                "Competing Traffic Preset",
                options=["None (0 pkts/s)", "Low (5 pkts/s)", "Moderate (15 pkts/s)", "High (30 pkts/s)"],
                index=1,
            )
            max_packet_size = st.selectbox("Max Packet Size / MTU (Bytes)", options=[64, 128, 256, 512], index=1)

        with col3:
            st.markdown("<b style='color: #38bdf8;'>Aggregation Strategy Rules</b>", unsafe_allow_html=True)
            fixed_batch_interval_s = st.slider("Fixed Batch Interval (s)", min_value=0.2, max_value=3.0, value=1.0, step=0.1)
            adaptive_max_wait_s = st.slider("Adaptive Max Wait (s)", min_value=0.2, max_value=2.0, value=0.8, step=0.1)
            adaptive_safety_slack_s = st.slider("Adaptive Slack Safety Margin (s)", min_value=0.05, max_value=0.8, value=0.25, step=0.05)
            seed = st.number_input("Reproducibility Seed", min_value=1, max_value=99999, value=42, step=1)
            exp_name = st.text_input("Experiment Label", value="IoT Cluster Simulation")

        submitted = st.form_submit_button("Run Complete Comparative Experiment", use_container_width=True)

    if submitted:
        preset_map = {
            "None (0 pkts/s)": CongestionPreset.NONE,
            "Low (5 pkts/s)": CongestionPreset.LOW,
            "Moderate (15 pkts/s)": CongestionPreset.MODERATE,
            "High (30 pkts/s)": CongestionPreset.HIGH,
        }
        cfg = ExperimentConfig(
            num_sensors=num_sensors,
            reading_rate_hz=reading_rate_hz,
            baseline_deadline_s=baseline_deadline_s,
            duration_s=duration_s,
            bandwidth_kbps=bandwidth_kbps,
            packet_loss_rate=packet_loss_rate,
            congestion_preset=preset_map[congestion_option],
            max_packet_size=max_packet_size,
            fixed_batch_interval_s=fixed_batch_interval_s,
            adaptive_max_wait_s=adaptive_max_wait_s,
            adaptive_safety_slack_s=adaptive_safety_slack_s,
            seed=int(seed),
            name=exp_name.strip() or "Custom IoT Run",
        )

        with st.spinner("Executing discrete-event simulation across all 3 strategies..."):
            new_result = ExperimentRunner.run_experiment(cfg)
            save_experiment_result(new_result)
            st.session_state["current_result"] = new_result
            st.success(f"Experiment executed successfully! Active experiment ID: {new_result.experiment_id}")
            st.rerun()

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 2. Saved Experiments History & Data Management
    st.subheader("Persistent Experiment Library", anchor=False)
    saved_list = list_saved_experiments()

    if saved_list:
        df_saved = pd.DataFrame(saved_list)
        st.dataframe(
            df_saved,
            column_config={
                "id": st.column_config.TextColumn("Experiment ID", width="medium"),
                "created_at": st.column_config.TextColumn("Timestamp", width="medium"),
                "name": st.column_config.TextColumn("Experiment Name", width="medium"),
                "duration_s": st.column_config.NumberColumn("Duration (s)", format="%.1fs"),
                "num_sensors": st.column_config.NumberColumn("Sensors", format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # Action bar to load or delete saved experiments
        col_select, col_load, col_csv_m, col_csv_d, col_delete = st.columns([2, 1, 1, 1, 1])

        with col_select:
            selected_id = st.selectbox(
                "Select Experiment from Library",
                options=[s["id"] for s in saved_list],
                index=0,
            )

        with col_load:
            if st.button("Load Active"):
                saved_data = get_saved_experiment(selected_id)
                if saved_data and "config" in saved_data:
                    c = ExperimentConfig.from_dict(saved_data["config"])
                    re_res = ExperimentRunner.run_experiment(c)
                    re_res.experiment_id = selected_id
                    st.session_state["current_result"] = re_res
                    st.success(f"Loaded {selected_id} as active experiment.")
                    st.rerun()

        with col_csv_m:
            csv_metrics = export_metrics_to_csv_string(selected_id)
            if csv_metrics:
                st.download_button(
                    label="Metrics CSV",
                    data=csv_metrics.encode("utf-8"),
                    file_name=f"metrics_{selected_id}.csv",
                    mime="text/csv",
                )

        with col_csv_d:
            csv_decisions = export_decisions_to_csv_string(selected_id)
            if csv_decisions:
                st.download_button(
                    label="Decisions CSV",
                    data=csv_decisions.encode("utf-8"),
                    file_name=f"decisions_{selected_id}.csv",
                    mime="text/csv",
                )

        with col_delete:
            if st.button("Delete"):
                delete_saved_experiment(selected_id)
                st.info(f"Deleted experiment {selected_id}")
                st.rerun()

    else:
        st.info("No saved experiments found in SQLite database.")


render_experiment_setup()
