"""
============================================================
Smart Land Management Copilot — Matchmaking View
============================================================
Renders the matchmaking compatibility report with visual cards,
progress bars, and LLM analysis integration.

Design Pattern: View (MVP)
SOLID: SRP — matchmaking report rendering only
============================================================
"""

from __future__ import annotations

import streamlit as st
from typing import Dict, Any, List

from services.state_manager import get_state
from services.matchmaking_service import get_matchmaking_service
from services.glm_service import get_glm_service
from ui.components import (
    render_compatibility_bar, render_auction_card,
    render_match_card, compat_color,
)
from models.investor import InvestorCriteria


def render_matchmaking_view() -> None:
    """
    Render the matchmaking compatibility report.

    This is displayed in an expander below the main content area,
    and also pushed to the chat when LLM analysis is triggered.
    """
    state = get_state()

    if not state.matchmaking.report_data:
        return

    st.markdown("---")
    st.subheader("Matchmaking Compatibility Report")
    st.caption(f"Criteria: {state.matchmaking.criteria_summary}")

    results: List[Dict[str, Any]] = state.matchmaking.report_data

    # --- Top match highlight ---
    if results:
        top = results[0]
        compat = top.get("Compatibility_Percent", 0)
        st.markdown(
            f'<div style="background:linear-gradient(135deg,#0d3b0d,#1a5c1a);'
            f'border:2px solid {compat_color(compat)};border-radius:12px;'
            f'padding:16px;margin-bottom:12px;text-align:center;">'
            f'<div style="font-size:12px;color:#aaa;">TOP MATCH</div>'
            f'<div style="font-size:24px;font-weight:bold;color:{compat_color(compat)};">'
            f'{top.get("Land_ID", "")} — {compat}%</div>'
            f'<div style="font-size:13px;color:#bbb;">'
            f'{top.get("Governorate", "")} — {top.get("Region_City", "")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # --- All result cards ---
    for i, result in enumerate(results):
        render_match_card(result, i)

    # --- Auction opportunities section ---
    auction_results = [r for r in results if r.get("is_auction", False)]
    if auction_results:
        st.markdown("---")
        st.subheader("Auction Opportunities")
        st.caption("Lands available via public auction with special pricing")
        for result in auction_results:
            render_auction_card(result)

    # --- LLM Analysis Button ---
    st.markdown("---")
    col_btn, col_status = st.columns([1, 2])
    with col_btn:
        analyze_btn = st.button(
            "AI Analysis",
            type="primary",
            use_container_width=True,
            disabled=state.matchmaking.llm_analysis_done,
        )
    with col_status:
        if state.matchmaking.llm_analysis_done:
            st.success("Analysis complete — check chat")
        else:
            st.info("Click to send results to GLM for AI analysis")

    if analyze_btn and not state.matchmaking.llm_analysis_done:
        _run_llm_analysis(state)


def _run_matchmaking(criteria: InvestorCriteria, state) -> None:
    """
    Execute the matchmaking pipeline.

    Pipeline: Criteria → MatchmakingService → Display → Chat
    """
    matchmaking_svc = get_matchmaking_service()
    report = matchmaking_svc.match(criteria)

    # Format results for display
    display_results = [r.to_display_dict() for r in report.results]
    state.matchmaking.set_results(
        report_data=display_results,
        criteria_summary=report.criteria_summary,
        context_text=matchmaking_svc.format_for_llm(report),
    )


def _run_llm_analysis(state) -> None:
    """Send matchmaking results to GLM for AI analysis."""
    glm_service = get_glm_service()

    # Add user context message to chat
    state.chat.add_user_message(
        f"[Matchmaking Analysis] Criteria: {state.matchmaking.criteria_summary}"
    )

    # Stream analysis
    with st.chat_message("assistant"):
        response_stream = st.write_stream(
            glm_service.stream_matchmaking(
                criteria_summary=state.matchmaking.criteria_summary,
                context_text=state.matchmaking.context_text,
            )
        )

    state.chat.add_assistant_message(response_stream)
    state.matchmaking.llm_analysis_done = True