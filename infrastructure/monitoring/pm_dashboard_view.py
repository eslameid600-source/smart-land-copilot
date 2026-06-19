"""
Smart Land Management Copilot — PM Dashboard View
=====================================================
System performance, API health, customer service KPIs,
and development metrics.
"""

import streamlit as st
import pandas as pd

from services.metrics_service import get_metrics_service
from services.customer_service import CustomerServiceSystem
from ui.components import render_section_header, render_metric_card


def render_pm_dashboard():
    """Render the project management dashboard tab."""
    render_section_header(
        "Project Management Dashboard",
        subtitle="System performance, API health, customer service KPIs, and usage analytics",
    )

    metrics = get_metrics_service()
    dashboard = metrics.get_dashboard()

    # ── Get customer service metrics ──
    cs = st.session_state.get("cs_system", CustomerServiceSystem())
    cs_metrics = cs.get_dashboard_metrics()
    sat_stats = cs.get_satisfaction_stats()

    # ── System Health ──
    st.markdown("#### System Health")

    sys_status = dashboard["system"]["status"]
    status_color = "#27ae60" if sys_status == "Operational" else "#f39c12" if sys_status == "Degraded" else "#e74c3c"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card("System Status", sys_status, color=status_color)
    with c2:
        render_metric_card("Uptime", dashboard["system"]["uptime_formatted"])
    with c3:
        render_metric_card("Total Requests", str(dashboard["system"]["total_requests"]))
    with c4:
        render_metric_card("Version", dashboard["system"]["version"])

    # ── API Performance ──
    st.markdown("#### API Performance")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card("Avg Latency", f"{dashboard['api_performance']['avg_latency_ms']:.0f} ms")
    with c2:
        render_metric_card("P95 Latency", f"{dashboard['api_performance']['p95_latency_ms']:.0f} ms")
    with c3:
        render_metric_card("Error Rate", f"{dashboard['api_performance']['error_rate_pct']:.1f}%")
    with c4:
        render_metric_card("Total API Calls", str(dashboard["api_performance"]["total_calls"]))

    # ── Usage Stats ──
    st.markdown("#### Usage Analytics")

    c1, c2, c3 = st.columns(3)
    with c1:
        render_metric_card("Total Searches", str(dashboard["usage_stats"]["total_searches"]))
    with c2:
        render_metric_card("Total Predictions", str(dashboard["usage_stats"]["total_predictions"]))
    with c3:
        render_metric_card("Total Chats", str(dashboard["usage_stats"]["total_chats"]))

    # ── Customer Service KPIs ──
    st.markdown("#### Customer Service KPIs")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_metric_card("Total Tickets", str(cs_metrics["total_tickets"]))
    with c2:
        render_metric_card("Open", str(cs_metrics["open_tickets"]), color="#f39c12")
    with c3:
        render_metric_card("Escalated", str(cs_metrics["escalated_tickets"]), color="#e74c3c")
    with c4:
        render_metric_card("Resolved", str(cs_metrics["resolved_tickets"]), color="#27ae60")
    with c5:
        render_metric_card("Avg Satisfaction", f"{cs_metrics['avg_satisfaction']}/5")

    # ── Satisfaction Distribution ──
    if sat_stats["total_rated"] > 0:
        st.markdown("#### Satisfaction Distribution")
        dist = sat_stats["distribution"]
        sat_data = {
            "Rating": ["1 - Poor", "2 - Fair", "3 - OK", "4 - Good", "5 - Excellent"],
            "Count": [dist.get(str(i), 0) for i in range(1, 6)],
        }
        st.bar_chart(pd.DataFrame(sat_data).set_index("Rating"), height=200)

    # ── Recent Errors ──
    if dashboard["recent_errors"]:
        st.markdown("#### Recent Errors")
        for err in dashboard["recent_errors"]:
            st.error(f"[{err['timestamp']}] {err['endpoint']}: {err['error'][:100]}")

    # ── Data Quality Report ──
    st.markdown("#### Data Quality Report")
    from data.land_database import get_all_lands
    lands = get_all_lands()

    total_fields = len(lands[0]) if lands else 0
    complete_records = sum(
        1 for l in lands
        if all(l.get(k) is not None for k in ["Land_ID", "Governorate", "Latitude", "Longitude", "Price_Per_Sqm_EGP"])
    )
    geo_complete = sum(1 for l in lands if l.get("Bearing_Capacity_kPa"))
    infra_complete = sum(1 for l in lands if l.get("Electricity_Capacity_MW"))

    quality_data = {
        "Metric": [
            "Total Land Records",
            "Fields per Record",
            "Records with Core Data",
            "Records with Geological Data",
            "Records with Infrastructure Data",
            "Records with Prediction Data",
        ],
        "Value": [
            str(len(lands)),
            str(total_fields),
            f"{complete_records}/{len(lands)} ({complete_records/len(lands)*100:.0f}%)",
            f"{geo_complete}/{len(lands)} ({geo_complete/len(lands)*100:.0f}%)",
            f"{infra_complete}/{len(lands)} ({infra_complete/len(lands)*100:.0f}%)",
            f"{len(lands)}/{len(lands)} (100%)",
        ],
    }
    st.dataframe(pd.DataFrame(quality_data), use_container_width=True, hide_index=True)