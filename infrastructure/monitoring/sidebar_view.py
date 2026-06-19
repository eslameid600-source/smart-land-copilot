"""
Smart Land Management Copilot — Sidebar View
==============================================
Dashboard stats, matchmaking form, and data filters.
"""

import streamlit as st
from typing import Optional, List

from data.land_database import (
    summary_stats, get_usage_categories, get_governorates,
    get_land_dataframe, USAGE_COLORS, ALL_UTILITIES,
)
from rag.search_engine import proactive_match, format_context_for_llm


def render_sidebar() -> Optional[dict]:
    """Render the full sidebar. Returns investor criteria dict if form submitted."""

    with st.sidebar:
        # ── Account Panel ──
        from services.user_service import get_user_service
        user_svc = get_user_service()

        if "current_user_id" in st.session_state:
            current_user = user_svc.get_user(st.session_state["current_user_id"])
            if current_user:
                role_colors = {
                    "Buyer/Investor": "#27ae60",
                    "Seller/Owner": "#2980b9",
                    "Certified Broker": "#f39c12",
                }
                color = role_colors.get(current_user.role.value, "#888")
                verification_badge = ""
                if current_user.role.value == "Certified Broker":
                    status_color = "#27ae60" if current_user.is_broker_verified else "#e74c3c"
                    verification_badge = (
                        f'<div style="color:{status_color};font-size:11px;margin-top:2px;">'
                        f'{current_user.broker_verification_status.value}</div>'
                    )
                st.markdown(
                    f"""
                    <div style="background:#1a1a2e;border:1px solid {color}40;
                                border-radius:8px;padding:10px 12px;margin-bottom:12px;">
                        <div style="font-size:11px;color:#888;text-transform:uppercase;">
                            {current_user.role.value}
                        </div>
                        <div style="font-weight:600;color:{color};font-size:14px;">
                            {current_user.full_name}
                        </div>
                        {verification_badge}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Switch Account", key="sidebar_switch_btn", use_container_width=True):
                    del st.session_state["current_user_id"]
                    st.rerun()
        else:
            st.markdown(
                '<div style="background:#1a1a2e;border:1px solid #333;'
                'border-radius:8px;padding:10px 12px;margin-bottom:12px;text-align:center;">'
                '<div style="color:#888;font-size:12px;">No account selected</div>'
                '<div style="color:#bbb;font-size:13px;">Select a role below to continue</div>'
                '</div>',
                unsafe_allow_html=True,
            )

            # Quick role selection in sidebar
            quick_roles = ["Buyer/Investor", "Seller/Owner", "Certified Broker"]
            for role_name in quick_roles:
                users = user_svc.list_users()
                matching = [u for u in users if u.role.value == role_name]
                if matching:
                    if st.button(
                        f"Login as {role_name}",
                        key=f"sidebar_login_{role_name.replace('/', '_').replace(' ', '_')}",
                        use_container_width=True,
                    ):
                        st.session_state["current_user_id"] = matching[0].user_id
                        st.rerun()

        st.divider()

        # ── Dashboard Stats ──
        st.markdown("### Dashboard")
        stats = summary_stats()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Lands", stats["total_lands"])
            st.metric("Auctions", stats["auction_lands"])
        with col2:
            st.metric("Avg Price/m\u00b2", f"{stats['avg_price_per_sqm']:,.0f} EGP")
            st.metric("Total Area", f"{stats['total_area_sqm']:,} m\u00b2")

        st.metric("Total Portfolio Value", f"{stats['total_value_egp']:,.0f} EGP")

        # Marketplace stats
        from services.auction_service import get_auction_engine, get_sourcing_service
        try:
            eng = get_auction_engine()
            src = get_sourcing_service()
            auc_count = len(eng.list_auctions())
            lead_stats = src.get_lead_stats()
            col3, col4 = st.columns(2)
            with col3:
                st.metric("Active Auctions", auc_count)
            with col4:
                st.metric("Scout Leads", lead_stats["total_leads"])
        except Exception:
            pass

        # Usage breakdown
        st.markdown("**Usage Breakdown**")
        for usage, count in stats["usage_breakdown"].items():
            color = USAGE_COLORS.get(usage, "#95a5a6")
            st.markdown(
                f'<span style="color:{color};">●</span> {usage}: **{count}** lands',
                unsafe_allow_html=True,
            )

        st.divider()

        # ── Investor Matchmaking Form ──
        st.markdown("### Investor Matchmaking")
        st.caption("Find lands matching your criteria")

        usage_options = ["Any"] + get_usage_categories()
        gov_options = ["Any"] + get_governorates()

        target_usage = st.selectbox("Land Usage", usage_options, index=0)
        preferred_gov = st.selectbox("Preferred Governorate", gov_options, index=0)

        min_area = st.number_input(
            "Min Area (sqm)", min_value=0, max_value=10_000_000, value=0,
            step=10000, format="%d",
        )
        max_price = st.number_input(
            "Max Price/m\u00b2 (EGP)", min_value=0, max_value=100_000, value=0,
            step=100, format="%d",
        )

        required_utils = st.multiselect("Required Utilities", ALL_UTILITIES)

        submitted = st.button("Find Matching Lands", type="primary", use_container_width=True)

        if submitted:
            criteria = {
                "target_usage": target_usage if target_usage != "Any" else None,
                "preferred_gov": preferred_gov if preferred_gov != "Any" else None,
                "min_area": min_area if min_area > 0 else None,
                "max_price_per_sqm": max_price if max_price > 0 else None,
                "required_utilities": required_utils if required_utils else None,
            }

            # Run matchmaking
            results = proactive_match(
                target_usage=criteria["target_usage"],
                min_area=criteria["min_area"],
                max_price_per_sqm=criteria["max_price_per_sqm"],
                required_utilities=criteria["required_utilities"],
                preferred_gov=criteria["preferred_gov"],
            )

            # Store in session state
            st.session_state["matchmaking_results"] = results
            st.session_state["matchmaking_criteria"] = criteria
            st.rerun()

        # Show results if available
        if "matchmaking_results" in st.session_state:
            st.divider()
            st.markdown("### Match Results")
            results = st.session_state["matchmaking_results"]

            for r in results[:5]:
                compat = r["Compatibility_Percent"]
                color = "#27ae60" if compat >= 70 else "#f39c12" if compat >= 40 else "#e74c3c"
                st.markdown(
                    f"""
                    <div style="background:#1a1a2e;border-left:3px solid {color};
                                padding:8px 12px;border-radius:4px;margin-bottom:6px;">
                        <b>{r['Land_ID']}</b> — {r['Region_City']}
                        <span style="float:right;color:{color};font-weight:700;">{compat}%</span><br>
                        <small>{r['Allowed_Usage']} | {r['Total_Area_Sqm']:,} m\u00b2 |
                        {r['Price_Per_Sqm_EGP']:,} EGP/m\u00b2</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if len(results) > 5:
                st.caption(f"...and {len(results) - 5} more lands")

        st.divider()

        # ── Data Table Toggle ──
        if st.checkbox("Show Raw Data Table"):
            df = get_land_dataframe()
            display_cols = [
                "Land_ID", "Governorate", "Region_City", "Total_Area_Sqm",
                "Price_Per_Sqm_EGP", "Allowed_Usage", "Investment_Status",
            ]
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)