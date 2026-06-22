"""
Smart Land Management Copilot — Buyer/Investor View
====================================================
Asset tracking portfolio (إدارة أملاك) displaying land pricing trends,
infrastructure availability, and multi-use classifications.
"""

from typing import Dict

import pandas as pd
import streamlit as st

from data.land_database import get_all_lands
from ui.components import (render_land_card, render_metric_card,
                           render_section_header)


def render_buyer_view():
    """
    Render the Buyer/Investor dashboard with portfolio tracking,
    watchlist, and infrastructure analysis.
    """
    from services.auction_service import get_auction_engine
    from services.environmental_service import get_environmental_service
    from services.user_service import get_user_service

    user_svc = get_user_service()
    env_svc = get_environmental_service()
    auction_engine = get_auction_engine()

    current_user = _get_current_buyer(user_svc)
    if not current_user:
        st.warning("No Buyer/Investor account selected. Please log in from the account panel.")
        return

    render_section_header(
        f"Asset Portfolio — {current_user.full_name}",
        subtitle="Track pricing trends, infrastructure, and multi-use classifications",
    )

    lands = get_all_lands()
    land_map = {l["Land_ID"]: l for l in lands}

    # ── Portfolio Metrics ──
    portfolio_ids = current_user.portfolio_land_ids
    watchlist_ids = current_user.watchlist_land_ids

    portfolio_lands = [land_map[lid] for lid in portfolio_ids if lid in land_map]
    watchlist_lands = [land_map[lid] for lid in watchlist_ids if lid in land_map]

    portfolio_value = sum(l["Total_Area_Sqm"] * l["Price_Per_Sqm_EGP"] for l in portfolio_lands)
    portfolio_area = sum(l["Total_Area_Sqm"] for l in portfolio_lands)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_metric_card("Portfolio Lands", str(len(portfolio_lands)), color="#27ae60")
    with m2:
        render_metric_card("Total Value", f"{portfolio_value:,.0f} EGP", color="#2980b9")
    with m3:
        render_metric_card("Total Area", f"{portfolio_area:,} m\u00b2", color="#f39c12")
    with m4:
        render_metric_card("Watchlist", str(len(watchlist_lands)), color="#e74c3c")

    st.markdown("---")

    # ── Tabs ──
    sub_tabs = st.tabs([
        "My Portfolio",
        "Watchlist",
        "Infrastructure Analysis",
        "Auction Bids",
    ])

    # ── TAB 1: MY PORTFOLIO ──
    with sub_tabs[0]:
        if not portfolio_lands:
            st.info("Your portfolio is empty. Add lands from the marketplace to start tracking.")
            _render_add_to_portfolio(lands, user_svc, current_user)
        else:
            for land in portfolio_lands:
                render_land_card(land)
                _render_infrastructure_badges(land)

                # Environmental analysis
                env_data = env_svc.analyze(land)
                if env_data.greenery:
                    _render_greenery_inline(env_data.greenery)
                if env_data.creator_studio:
                    _render_creator_score_inline(env_data.creator_studio)

            _render_add_to_portfolio(lands, user_svc, current_user)

    # ── TAB 2: WATCHLIST ──
    with sub_tabs[1]:
        if not watchlist_lands:
            st.info("No lands on your watchlist.")
        else:
            for land in watchlist_lands:
                render_land_card(land, compact=True)

        st.markdown("---")
        _render_add_to_watchlist(lands, user_svc, current_user)

    # ── TAB 3: INFRASTRUCTURE ANALYSIS ──
    with sub_tabs[2]:
        st.markdown("**Multi-Use Classification & Infrastructure Matrix**")
        all_utilities = ["Water", "Electricity", "Gas", "Fiber-Optic"]
        usage_list = sorted(set(l["Allowed_Usage"] for l in lands))

        sel_usage = st.selectbox("Filter by Usage", ["All"] + usage_list, key="buyer_usage_filter")
        filtered = lands if sel_usage == "All" else [l for l in lands if l["Allowed_Usage"] == sel_usage]

        rows = []
        for land in filtered:
            utils = land.get("Utilities_Availability", "")
            row = {
                "Land ID": land["Land_ID"],
                "Region": land["Region_City"],
                "Usage": land["Allowed_Usage"],
                "Area (m\u00b2)": land["Total_Area_Sqm"],
                "Price/m\u00b2 (EGP)": land["Price_Per_Sqm_EGP"],
                "Total (EGP)": land["Total_Area_Sqm"] * land["Price_Per_Sqm_EGP"],
            }
            for util in all_utilities:
                row[util] = "Available" if util in utils else "Not Available"
            rows.append(row)

        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── TAB 4: AUCTION BIDS ──
    with sub_tabs[3]:
        auctions = auction_engine.list_auctions()
        if not auctions:
            st.info("No auctions available.")
        else:
            for auction in auctions:
                status_color = "#27ae60" if auction.status.value == "Live" else "#95a5a6"
                st.markdown(
                    f"""
                    <div style="background:#1a1a2e;border-left:3px solid {status_color};
                                padding:12px 16px;border-radius:6px;margin-bottom:8px;">
                        <b>{auction.auction_id}</b> — {auction.region_city}
                        <span style="float:right;color:{status_color};">{auction.status.value}</span><br>
                        <small>Base: {auction.base_price_egp:,.0f} EGP |
                        Highest: {auction.current_highest_bid_egp:,.0f} EGP |
                        Bidders: {auction.registered_bidders_count}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def _get_current_buyer(user_svc):
    uid = st.session_state.get("current_user_id")
    if not uid:
        return None
    user = user_svc.get_user(uid)
    if user and user.role.value == "Buyer/Investor":
        return user
    return None


def _render_infrastructure_badges(land: Dict) -> None:
    """Render infrastructure availability as colored badges."""
    utils = land.get("Utilities_Availability", "")
    all_utils = ["Water", "Electricity", "Gas", "Fiber-Optic"]
    badges = ""
    for u in all_utils:
        color = "#27ae60" if u in utils else "#e74c3c"
        icon = "Yes" if u in utils else "No"
        badges += (
            f'<span style="background:{color}20;color:{color};padding:3px 10px;'
            f'border-radius:12px;font-size:11px;margin-right:6px;">{u}: {icon}</span>'
        )
    st.markdown(f'<div style="margin-top:6px;">{badges}</div>', unsafe_allow_html=True)


def _render_greenery_inline(greenery) -> None:
    """Render greenery index inline."""
    idx = greenery.greenery_density_index
    color = "#27ae60" if idx >= 60 else "#f39c12" if idx >= 30 else "#e74c3c"
    st.markdown(
        f"""
        <div style="margin-top:8px;padding:8px 12px;background:#1a1a2e;border-radius:6px;border-left:3px solid {color};">
            <small style="color:#888;">Greenery Density Index</small><br>
            <b style="color:{color};font-size:18px;">{idx:.1f}/100</b>
            <span style="color:#bbb;font-size:12px;margin-left:8px;">
                Nearest: {greenery.nearest_park_name} ({greenery.nearest_park_distance_km} km) |
                Parks 5km: {greenery.parks_within_5km}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_creator_score_inline(creator) -> None:
    """Render creator studio suitability inline."""
    score = creator.suitability_score
    color = "#27ae60" if score >= 60 else "#f39c12" if score >= 30 else "#e74c3c"
    st.markdown(
        f"""
        <div style="margin-top:4px;padding:8px 12px;background:#1a1a2e;border-radius:6px;border-left:3px solid {color};">
            <small style="color:#888;">Creator Studio Suitability</small><br>
            <b style="color:{color};font-size:18px;">{score:.1f}/100</b>
            <span style="color:#bbb;font-size:12px;margin-left:8px;">
                Fiber: {'Yes' if creator.fiber_optic_available else 'No'} |
                Speed: {creator.internet_speed_mbps} Mbps |
                Noise: {creator.noise_level_rating}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_add_to_portfolio(lands, user_svc, user):
    """Render form to add lands to portfolio."""
    with st.expander("Add Land to Portfolio"):
        options = {f"{l['Land_ID']} — {l['Region_City']}" : l["Land_ID"] for l in lands}
        sel = st.selectbox("Select Land", list(options.keys()), key="portfolio_add_land")
        if st.button("Add to Portfolio", key="portfolio_add_btn"):
            land_id = options[sel]
            user_svc.add_to_portfolio(user.user_id, land_id)
            st.success(f"Added {land_id} to portfolio")
            st.rerun()


def _render_add_to_watchlist(lands, user_svc, user):
    """Render form to add lands to watchlist."""
    with st.expander("Add Land to Watchlist"):
        options = {f"{l['Land_ID']} — {l['Region_City']}" : l["Land_ID"] for l in lands}
        sel = st.selectbox("Select Land", list(options.keys()), key="watchlist_add_land")
        if st.button("Add to Watchlist", key="watchlist_add_btn"):
            land_id = options[sel]
            user_svc.add_to_watchlist(user.user_id, land_id)
            st.success(f"Added {land_id} to watchlist")
            st.rerun()