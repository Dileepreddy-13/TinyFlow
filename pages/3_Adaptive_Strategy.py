"""
TinyFlow — Adaptive Strategy Decision Monitor.
Inspects real-time internal state, decision-making logic, and genuine algorithm explanations.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd

from tinyflow.models import DecisionAction, DecisionReasonCode
from tinyflow.ui_shared import apply_shared_theme, get_or_create_active_result, render_experiment_header_banner
from tinyflow.visualization.plots import (
    create_adaptive_reasons_chart,
    create_buffer_occupancy_timeline,
)


def render_adaptive_strategy():
    try:
        st.set_page_config(
            page_title="TinyFlow — Adaptive Decision Monitor",
            layout="wide",
        )
    except Exception:
        pass
    apply_shared_theme()

    result = get_or_create_active_result()
    cfg = result.config
    trace = result.traces["Adaptive"]
    decisions = trace.decisions
    m = trace.metrics

    st.title("Strategy: Adaptive Aggregation Decision Monitor", anchor=False)
    st.markdown(
        "<p style='color: #94a3b8; font-size: 1rem; margin-top: -10px; margin-bottom: 18px;'>"
        "Real-time evaluation of buffer capacity, network queue congestion, reading urgency, and delivery deadlines."
        "</p>",
        unsafe_allow_html=True,
    )

    render_experiment_header_banner(result)

    # 1. Latest Decision Monitor Panel
    latest_dec = decisions[-1] if decisions else None

    if latest_dec:
        action_color = "#10b981" if latest_dec.action == DecisionAction.TRANSMIT else "#38bdf8"
        action_bg = "rgba(16, 185, 129, 0.15)" if latest_dec.action == DecisionAction.TRANSMIT else "rgba(56, 189, 248, 0.15)"

        st.markdown(
            f"""
            <div style="background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 18px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <span style="font-size: 0.8rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;">LATEST ALGORITHM DECISION AT T = {latest_dec.timestamp:.3f}s</span>
                    </div>
                    <div>
                        <span style="background-color: {action_bg}; color: {action_color}; border: 1px solid {action_color}; padding: 4px 12px; border-radius: 4px; font-weight: 700; font-size: 0.85rem;">
                            ACTION: {latest_dec.action.value}
                        </span>
                    </div>
                </div>
                <div style="background-color: #0f172a; border-left: 4px solid {action_color}; padding: 12px 14px; border-radius: 3px; margin-bottom: 14px;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #93c5fd; font-weight: 600;">[{latest_dec.reason_code.value}]</span>
                    <p style="color: #f1f5f9; font-size: 0.92rem; margin: 6px 0 0 0; line-height: 1.5;">{latest_dec.reason_text}</p>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; font-size: 0.82rem; color: #cbd5e1;">
                    <div style="background-color: #0f172a; padding: 8px 12px; border-radius: 4px; border: 1px solid #334155;">
                        <span style="color: #94a3b8; display: block;">Buffer Occupancy</span>
                        <b style="color: #f8fafc; font-size: 1rem;">{latest_dec.buffer_count} readings</b> ({latest_dec.buffer_bytes}B / {cfg.max_packet_size}B)
                    </div>
                    <div style="background-color: #0f172a; padding: 8px 12px; border-radius: 4px; border: 1px solid #334155;">
                        <span style="color: #94a3b8; display: block;">Oldest Reading Age</span>
                        <b style="color: #f8fafc; font-size: 1rem;">{latest_dec.oldest_reading_age:.3f} s</b> (Limit: {cfg.adaptive_max_wait_s:.2f}s)
                    </div>
                    <div style="background-color: #0f172a; padding: 8px 12px; border-radius: 4px; border: 1px solid #334155;">
                        <span style="color: #94a3b8; display: block;">Min Deadline Slack</span>
                        <b style="color: #f8fafc; font-size: 1rem;">{latest_dec.min_slack:.3f} s</b> (Safety: {cfg.adaptive_safety_slack_s:.2f}s)
                    </div>
                    <div style="background-color: #0f172a; padding: 8px 12px; border-radius: 4px; border: 1px solid #334155;">
                        <span style="color: #94a3b8; display: block;">Queue Congestion</span>
                        <b style="color: #f8fafc; font-size: 1rem;">{latest_dec.queue_occupancy} pkts</b> (Est Delay: {latest_dec.estimated_queue_delay * 1000.0:.1f} ms)
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 2. Charts Row: Reason Breakdown & Buffer Dynamics
    col_chart_left, col_chart_right = st.columns(2)

    with col_chart_left:
        fig_reasons = create_adaptive_reasons_chart(decisions)
        st.plotly_chart(fig_reasons, use_container_width=True)

    with col_chart_right:
        fig_buf = create_buffer_occupancy_timeline(decisions)
        st.plotly_chart(fig_buf, use_container_width=True)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 3. Decision Rules & Policy Documentation
    with st.expander("Documented Adaptive Policy Decision Rules & Thresholds", expanded=False):
        st.markdown(
            f"""
            The Adaptive Aggregator evaluates incoming events (reading arrivals and timer ticks) against the following hierarchical policy:
            
            1. **Urgent Priority Rule:** If any buffered reading has priority `CRITICAL` (or `HIGH` when enabled), immediately trigger `TRANSMIT`. Ensures life-critical or emergency alarm readings are never delayed.
            2. **Buffer MTU Capacity Rule:** If adding another reading would exceed the link MTU limit ({cfg.max_packet_size} bytes), transmit immediately. Prevents unnecessary frame fragmentation and maximizes byte packaging efficiency.
            3. **Deadline Slack Rule:** Computes effective delivery slack: $\\text{{slack}}_{{min}} - (\\text{{est\\_queue\\_delay}} + \\text{{tx\\_delay}})$. If effective slack $\\le$ safety margin ({cfg.adaptive_safety_slack_s}s), transmit immediately to guarantee arrival before deadline expiry.
            4. **Dynamic Max Wait Rule:** If the oldest reading has been buffered for $\\ge {cfg.adaptive_max_wait_s}s$ (dynamically scaled down during elevated queue congestion), transmit to bound latency.
            5. **Congestion Backlog Rule:** If link queue depth $\\ge {cfg.adaptive_queue_threshold}$ packets and buffer has $\\ge 3$ readings, transmit immediately to avoid downstream queue delay cascades.
            6. **Holding Rule (Default):** If none of the above thresholds are violated, choose `WAIT` to accumulate additional readings and amortize packet-header overhead.
            """
        )

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # 4. Filterable Decision Log Table
    st.subheader("Decision History Audit Log", anchor=False)
    col_filter_action, col_filter_reason = st.columns([1, 2])

    with col_filter_action:
        action_filter = st.selectbox("Filter by Action", ["All", "TRANSMIT only", "WAIT only"])

    all_reason_codes = sorted(list({d.reason_code.value for d in decisions}))
    with col_filter_reason:
        reason_filter = st.selectbox("Filter by Reason Trigger", ["All"] + all_reason_codes)

    filtered_decisions = decisions
    if action_filter == "TRANSMIT only":
        filtered_decisions = [d for d in filtered_decisions if d.action == DecisionAction.TRANSMIT]
    elif action_filter == "WAIT only":
        filtered_decisions = [d for d in filtered_decisions if d.action == DecisionAction.WAIT]

    if reason_filter != "All":
        filtered_decisions = [d for d in filtered_decisions if d.reason_code.value == reason_filter]

    st.caption(f"Displaying {len(filtered_decisions)} of {len(decisions)} decision events")

    if filtered_decisions:
        df_dec = pd.DataFrame([
            {
                "Time (s)": f"{d.timestamp:.3f}",
                "Action": d.action.value,
                "Reason Trigger": d.reason_code.value,
                "Explanation": d.reason_text,
                "Buffer Count": d.buffer_count,
                "Buffer Bytes": f"{d.buffer_bytes} B",
                "Oldest Age": f"{d.oldest_reading_age:.3f} s",
                "Min Slack": f"{d.min_slack:.3f} s",
                "Queue Pkts": d.queue_occupancy,
                "Packet ID": d.packet_id or "—",
            }
            for d in filtered_decisions[:200]
        ])
        st.dataframe(df_dec, use_container_width=True, hide_index=True)


render_adaptive_strategy()
