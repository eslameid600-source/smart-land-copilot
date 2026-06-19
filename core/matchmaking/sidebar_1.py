"""
============================================================
Smart Land Management Copilot — Sidebar View
============================================================
Renders the sidebar with dashboard metrics, map filter,
governor breakdown, and the investor matchmaking form.

Design Pattern: View (MVP), Component Composition
SOLID: SRP — sidebar rendering only
============================================================
"""

from __future__ import annotations

import streamlit as st
from typing import List, Optional

from services.state_manager import get_state
from services.analytics_service import get_analytics_service
from services.matchmaking_service import get_matchmaking_service
from services.glm_service import get_glm_service
from services.rag_service import get_rag_service
from ui.components import (
    render_metric_card, render_map_legend, render_compatibility_bar,
    render_auction_card, render_match_card,
)
from ui.matchmaking_view import run_matchmaking
from models.land import ALL_UTILITIES
from models.investor import InvestorCriteria


def render_sidebar() -> None:
    """
    Render the complete sidebar content.

    Called from app.py as the single entry point for sidebar rendering.
    """
    state = get_state()
    analytics = get_analytics_service()

    st.title("Land Copilot")
    st.caption("Egypt Investment Land Advisory")
    st.markdown("---")

    # --- Database Overview ---
    _render_dashboard_metrics(analytics)

    st.markdown("---")

    # --- Map Legend ---
    render_map_legend()

    st.markdown("---")

    # --- Map Filter ---
    _render_map_filter()

    st.markdown("---")

    # --- Governorate Breakdown ---
    _render_governorate_breakdown(analytics)

    st.markdown("---")

    # --- Investor Matchmaking Form ---
    _render_matchmaking_form(state)


def _render_dashboard_metrics(analytics) -> None:
    """Render the key metrics section."""
    st.subheader("Database Overview")
    stats = analytics.get_summary()

    col_a, col_b = st.columns(2)
    with col_a:
        render_metric_card("Total Lands", str(stats.total_lands), "#3498db")
    with col_b:
        render_metric_card("Auctions", str(stats.auction_lands), "#f39c12")

    render_metric_card(
        "Total Area",
        f"{stats.total_area_sqm:,} sqm",
        "#2ecc71",
    )
    render_metric_card(
        "Avg Price/sqm",
        f"{stats.avg_price_per_sqm:,.0f} EGP",
        "#e74c3c",
    )

    # Usage breakdown mini-bars
    st.markdown("**Usage Breakdown**")
    total = max(stats.total_lands, 1)
    for usage, count in sorted(stats.usage_breakdown.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total) * 100
        st.markdown(
            f"<div style='margin:2px 0;font-size:12px;'>"
            f"<b>{usage}</b> <span style='color:#888;'>({count})</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.progress(count / total)


def _render_map_filter() -> None:
    """Render the map usage type filter."""
    analytics = get_analytics_service()
    state = get_state()

    st.subheader("Filter Map by Type")
    categories = ["All"] + analytics.get_usage_categories()
    current = state.map.selected_usage_filter

    new_filter = st.radio(
        "Show on map:",
        options=categories,
        index=categories.index(current) if current in categories else 0,
        label_visibility="collapsed",
        horizontal=False,
    )

    if new_filter != current:
        state.map.set_filter(new_filter)


def _render_governorate_breakdown(analytics) -> None:
    """Render the governorate breakdown data table."""
    st.subheader("Governorate Breakdown")
    df = analytics.get_governorate_dataframe()
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)


def _render_matchmaking_form(state) -> None:
    """
    Render the Proactive Investor Matchmaking form.

    This is the main new feature: a structured form where
    investors specify their criteria, click "Match", and
    get a ranked compatibility report.
    """
    st.subheader("Investor Matchmaking")

    with st.form("matchmaking_form", clear_on_submit=False):
        target_usage = st.selectbox(
            "Target Usage Type",
            options=["(Any)"] + ["Industrial", "Agricultural", "Logistics", "Residential"],
            format_func=lambda x: "Any Type" if x == "(Any)" else x,
        )

        col_area, col_price = st.columns(2)
        with col_area:
            min_area = st.number_input(
                "Min Area (sqm)",
                min_value=0,
                max_value=10_000_000,
                value=0,
                step=10_000,
            )
        with col_price:
            max_price = st.number_input(
                "Max Price (EGP/sqm)",
                min_value=0,
                max_value=100_000,
                value=0,
                step=100,
            )

        required_utils = st.multiselect(
            "Required Utilities",
            options=ALL_UTILITIES,
            default=[],
        )

        submitted = st.form_submit_button(
            "Match My Criteria",
            type="primary",
            use_container_width=True,
        )

        if submitted:
            criteria = InvestorCriteria(
                target_usage=target_usage if target_usage != "(Any)" else None,
                min_area_sqm=min_area if min_area > 0 else None,
                max_price_per_sqm=max_price if max_price > 0 else None,
                required_utilities=required_utils,
            )
            run_matchmaking(criteria, state)