"""
Smart Land Management Copilot — Auction & Marketplace View
============================================================
Full auction dashboard with live bidding, financial breakdown
tables, land sourcing workflow, and scout management.
"""

import pandas as pd
import streamlit as st
from data.land_database import get_all_lands

from services.auction_service import (
    CommissionCalculator,
    get_auction_engine,
    get_sourcing_service,
)
from ui.components import render_metric_card, render_section_header


def render_auction_view():
    """Render the Auction & Marketplace tab."""

    # Initialize services
    engine = get_auction_engine()
    sourcing_svc = get_sourcing_service()

    render_section_header(
        "Auction & Trading Marketplace",
        subtitle="Live auctions, transparent fee breakdowns, and land sourcing workflows",
    )

    sub_tabs = st.tabs([
        "Live Auctions",
        "Place Bid",
        "Financial Breakdown",
        "Scout Leads",
    ])

    # ═══════════════════════════════════════════
    # TAB 1: LIVE AUCTIONS DASHBOARD
    # ═══════════════════════════════════════════
    with sub_tabs[0]:
        auctions = engine.list_auctions()

        # Marketplace summary metrics
        total_auctions = len(auctions)
        live_count = sum(1 for a in auctions if a.status.value == "Live")
        total_bids = sum(a.bid_count for a in auctions)
        total_bidders = sum(a.registered_bidders_count for a in auctions)
        highest_total = max(
            (a.current_highest_bid_egp for a in auctions if a.current_highest_bid_egp > 0),
            default=0,
        )

        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            render_metric_card("Total Auctions", str(total_auctions), color="#2980b9")
        with m2:
            render_metric_card("Live Now", str(live_count), color="#27ae60")
        with m3:
            render_metric_card("Total Bids", str(total_bids), color="#f39c12")
        with m4:
            render_metric_card("Registered Bidders", str(total_bidders))
        with m5:
            render_metric_card("Highest Bid", f"{highest_total:,.0f} EGP", color="#e74c3c")

        st.markdown("---")

        # Auction cards
        if not auctions:
            st.info("No auctions currently listed.")
        else:
            for auction in auctions:
                _render_auction_card(auction)

    # ═══════════════════════════════════════════
    # TAB 2: PLACE BID INTERFACE
    # ═══════════════════════════════════════════
    with sub_tabs[1]:
        live_auctions = engine.list_auctions()
        if not live_auctions:
            st.info("No active auctions to bid on.")
            return

        auction_options = {
            f"{a.auction_id} — {a.region_city} ({a.allowed_usage})": a
            for a in live_auctions
        }
        selected_key = st.selectbox("Select Auction", list(auction_options.keys()))
        auction = auction_options[selected_key]

        _render_auction_card(auction)

        if auction.status.value != "Live":
            st.warning("This auction is not currently accepting bids.")
        else:
            st.markdown("#### Place Your Bid")
            min_bid = auction.compute_minimum_next_bid()

            c1, c2 = st.columns(2)
            with c1:
                bidder_name = st.text_input("Bidder Name / Fund Name", value="", key="bidder_name")
            with c2:
                bidder_id = st.text_input("Bidder ID", value="", key="bidder_id")

            suggested_bid = round(min_bid * 1.01, 2)
            bid_amount = st.number_input(
                f"Bid Amount (EGP) — Minimum: {min_bid:,.0f} EGP",
                min_value=min_bid,
                max_value=min_bid * 5,
                value=suggested_bid,
                step=10000,
                format="%d",
                key="bid_amount_input",
            )

            if st.button("Submit Bid", type="primary", key="submit_bid_btn"):
                if not bidder_name or not bidder_id:
                    st.error("Please enter both Bidder Name and Bidder ID.")
                else:
                    bid, error = engine.place_bid(
                        auction_id=auction.auction_id,
                        bidder_id=bidder_id,
                        bidder_name=bidder_name,
                        bid_amount_egp=float(bid_amount),
                    )
                    if error:
                        st.error(f"Bid rejected: {error}")
                    else:
                        st.success(
                            f"Bid placed successfully! {bid.bid_amount_egp:,.0f} EGP "
                            f"({bid.bid_per_sqm_egp:,.2f} EGP/m\u00b2) — {bid.bid_id}"
                        )
                        st.rerun()

    # ═══════════════════════════════════════════
    # TAB 3: FINANCIAL BREAKDOWN
    # ═══════════════════════════════════════════
    with sub_tabs[2]:
        st.markdown(
            '<div style="background:#1a1a2e;border:1px solid #2980b9;padding:12px;'
            'border-radius:8px;margin-bottom:16px;">'
            '<span style="color:#2980b9;font-weight:600;">Transparent Fee Clearing</span> — '
            'Every party\'s exact financial cut from the transaction, '
            'including Egyptian Real Estate Disposal Tax '
            '(\u0636\u0631\u064a\u0628\u0629 \u0627\u0644\u062a\u0635\u0631\u0641\u0627\u062a \u0627\u0644\u0639\u0642\u0627\u0631\u064a\u0629), '
            'Shahr Eqary registration, and stamp duty.</div>',
            unsafe_allow_html=True,
        )

        lands = get_all_lands()
        land_options = {
            f"{ld['Land_ID']} — {ld['Region_City']} ({ld['Allowed_Usage']}) [{ld['Investment_Status']}]": ld
            for ld in lands
        }
        selected_land_key = st.selectbox("Select Land", list(land_options.keys()), key="fee_land_sel")
        land = land_options[selected_land_key]

        # Determine sale value
        auction = engine.get_auction_by_land(land["Land_ID"])
        if auction and auction.current_highest_bid_egp > 0:
            sale_value = auction.current_highest_bid_egp
            value_label = f"Current Highest Bid: {sale_value:,.0f} EGP"
        elif land["Investment_Status"] == "Public Auction" and land.get("Starting_Price_Per_Sqm_EGP"):
            sale_value = land["Starting_Price_Per_Sqm_EGP"] * land["Total_Area_Sqm"]
            value_label = f"Starting Price Total: {sale_value:,.0f} EGP"
        else:
            sale_value = land["Total_Price_EGP"]
            value_label = f"Direct Sale Price: {sale_value:,.0f} EGP"

        st.markdown(f"**{land['Land_ID']}** — {value_label}")

        # Custom commission overrides
        c1, c2 = st.columns(2)
        with c1:
            custom_platform = st.checkbox(
                "Custom Platform Commission",
                value=False,
                key="custom_plat_cb",
            )
            platform_pct = st.number_input(
                "Platform %", min_value=0.0, max_value=15.0, value=2.5,
                step=0.1, format="%.1f", disabled=not custom_platform, key="plat_pct_in",
            )
        with c2:
            custom_scout = st.checkbox(
                "Override Scout Eligibility",
                value=False,
                key="custom_scout_cb",
            )
            force_scout = st.checkbox(
                "Force Scout Fee",
                value=land.get("scout_fee_eligible", False),
                disabled=not custom_scout,
                key="force_scout_cb",
            )

        breakdown = CommissionCalculator.compute_breakdown(
            total_value_egp=sale_value,
            land_id=land["Land_ID"],
            auction_id=auction.auction_id if auction else None,
            is_auction=land["Investment_Status"] == "Public Auction",
            scout_name=land.get("scout_name", ""),
            scout_eligible=land.get("scout_fee_eligible", False) or (custom_scout and force_scout),
            custom_platform_pct=platform_pct if custom_platform else None,
        )

        # Render the transparent table
        rows = CommissionCalculator.format_breakdown_table(breakdown)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Summary metrics
        st.markdown("---")
        sm1, sm2, sm3 = st.columns(3)
        with sm1:
            render_metric_card(
                "Seller Net Proceeds",
                f"{breakdown.seller_net_proceeds_egp:,.0f} EGP",
                color="#27ae60",
                delta=f"{breakdown.seller_effective_pct:.1f}% of gross",
            )
        with sm2:
            render_metric_card(
                "Total Govt Duties",
                f"{breakdown.total_government_duties_egp:,.0f} EGP",
                color="#e74c3c",
                delta=f"{breakdown.real_estate_disposal_tax_pct + breakdown.registration_notary_fee_pct + breakdown.stamp_duty_pct:.1f}% total",
            )
        with sm3:
            render_metric_card(
                "Buyer Total Cost",
                f"{breakdown.buyer_total_cost_egp:,.0f} EGP",
                color="#f39c12",
            )

    # ═══════════════════════════════════════════
    # TAB 4: SCOUT LEADS & SOURCING
    # ═══════════════════════════════════════════
    with sub_tabs[3]:
        lead_stats = sourcing_svc.get_lead_stats()

        sm1, sm2, sm3, sm4 = st.columns(4)
        with sm1:
            render_metric_card("Total Leads", str(lead_stats["total_leads"]))
        with sm2:
            render_metric_card("Submitted", str(lead_stats["submitted"]))
        with sm3:
            render_metric_card("Docs Uploaded", str(lead_stats["documents_uploaded"]))
        with sm4:
            render_metric_card("Notary Verified", str(lead_stats["notary_verified"]))

        st.markdown("---")

        leads = sourcing_svc.list_leads()

        if not leads:
            st.info("No scout leads submitted yet.")
        else:
            for lead in leads:
                _render_lead_card(lead)

        # Submit new lead form
        st.markdown("#### Submit New Land Lead (Scout Mode)")
        with st.form("scout_lead_form"):
            sc1, sc2 = st.columns(2)
            with sc1:
                new_scout_name = st.text_input("Scout Name", value="", key="new_scout_name")
                new_scout_id = st.text_input("Scout ID", value="", key="new_scout_id")
                new_gov = st.text_input("Governorate", value="", key="new_gov")
                new_region = st.text_input("Region / City", value="", key="new_region")
            with sc2:
                new_area = st.number_input("Est. Area (sqm)", min_value=0, value=0, step=10000, key="new_area")
                new_price_sqm = st.number_input("Est. Price/sqm (EGP)", min_value=0, value=0, step=100, key="new_price_sqm")
                new_usage = st.selectbox("Allowed Usage", ["", "Industrial", "Logistics", "Agricultural", "Residential"], key="new_usage")
                new_soil = st.text_input("Soil Type", value="", key="new_soil")
                new_highways = st.text_input("Nearest Highways", value="", key="new_hw")
                new_description = st.text_area("Description / Notes", value="", key="new_desc")

            submitted = st.form_submit_button("Submit Lead", type="primary")
            if submitted:
                if not new_scout_name or not new_scout_id or not new_gov or not new_region:
                    st.error("Scout Name, Scout ID, Governorate, and Region are required.")
                else:
                    new_lead = sourcing_svc.submit_lead(
                        scout_id=new_scout_id,
                        scout_name=new_scout_name,
                        governorate=new_gov,
                        region_city=new_region,
                        estimated_area_sqm=new_area if new_area > 0 else None,
                        estimated_price_per_sqm_egp=new_price_sqm if new_price_sqm > 0 else None,
                        soil_type=new_soil,
                        allowed_usage=new_usage,
                        nearest_highways=new_highways,
                        description=new_description,
                    )
                    st.success(f"Lead submitted: {new_lead.lead_id}")
                    st.rerun()


def _render_auction_card(auction) -> None:
    """Render an auction as a styled card with bid information."""
    from data.land_database import USAGE_COLORS
    color = USAGE_COLORS.get(auction.allowed_usage, "#95a5a6")

    # Status color
    status_colors = {
        "Pending": "#f39c12", "Live": "#27ae60", "Ended": "#95a5a6", "Cancelled": "#e74c3c",
    }
    sc = status_colors.get(auction.status.value, "#95a5a6")
    time_left = auction.time_remaining() or ""

    scout_line = ""
    if auction.listing_source.value == "Scout Sourced" and auction.scout_name:
        scout_line = (
            f'<div style="margin-top:6px;font-size:12px;">'
            f'<span style="color:#f39c12;">Scout:</span> {auction.scout_name} '
            f'(1.5% sourcing fee)</div>'
        )

    st.markdown(
        f"""
        <div style="background:#1a1a2e;border-left:4px solid {color};
                    padding:16px;border-radius:8px;margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <b style="font-size:16px;color:{color};">{auction.auction_id}</b>
                    <span style="background:{sc}22;color:{sc};padding:2px 10px;
                                 border-radius:12px;font-size:12px;margin-left:8px;">
                        {auction.status.value}
                    </span>
                    {f'<span style="background:#e74c3c22;color:#e74c3c;padding:2px 10px;'
                     f'border-radius:12px;font-size:12px;margin-left:4px;">{time_left}</span>'
                     if time_left and time_left != "Ended" else ""}
                </div>
                <span style="background:{color}22;color:{color};padding:2px 10px;
                             border-radius:12px;font-size:12px;">
                    {auction.allowed_usage}
                </span>
            </div>
            <div style="color:#bbb;margin-top:6px;">
                {auction.governorate} — {auction.region_city}
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-top:12px;">
                <div><small style="color:#888;">Area</small><br><b>{auction.total_area_sqm:,} m\u00b2</b></div>
                <div><small style="color:#888;">Base Price</small><br><b>{auction.base_price_egp:,.0f} EGP</b></div>
                <div><small style="color:#888;">Highest Bid</small><br><b style="color:#27ae60;">{auction.current_highest_bid_egp:,.0f} EGP</b></div>
                <div><small style="color:#888;">Bidders / Bids</small><br><b>{auction.registered_bidders_count} / {auction.bid_count}</b></div>
            </div>
            {scout_line}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Show bid history
    if auction.all_bids:
        with st.expander(f"Bid History ({len(auction.all_bids)} bids)", expanded=False):
            bid_rows = []
            for b in reversed(auction.all_bids):
                status_emoji = ""
                if b.status.value == "Winning":
                    status_emoji = ">> "
                bid_rows.append({
                    "": status_emoji,
                    "Bidder": b.bidder_name,
                    "Amount (EGP)": f"{b.bid_amount_egp:,.0f}",
                    "Per sqm (EGP)": f"{b.bid_per_sqm_egp:,.2f}",
                    "Status": b.status.value,
                    "Time": b.bid_timestamp.split("T")[1][:8] if "T" in b.bid_timestamp else b.bid_timestamp[:19],
                })
            st.dataframe(pd.DataFrame(bid_rows), use_container_width=True, hide_index=True)


def _render_lead_card(lead) -> None:
    """Render a land sourcing lead as a styled card."""
    status_colors = {
        "Submitted": "#f39c12",
        "Documents Uploaded": "#2980b9",
        "Verified by Notary": "#27ae60",
        "Rejected": "#e74c3c",
    }
    sc = status_colors.get(lead.status.value, "#95a5a6")

    est_price = ""
    if lead.estimated_area_sqm and lead.estimated_price_per_sqm_egp:
        est_total = lead.estimated_area_sqm * lead.estimated_price_per_sqm_egp
        est_price = f" | Est. Total: {est_total:,.0f} EGP"

    st.markdown(
        f"""
        <div style="background:#1a1a2e;border-left:4px solid {sc};
                    padding:14px;border-radius:8px;margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <b style="color:{sc};">{lead.lead_id}</b>
                    <span style="background:{sc}22;color:{sc};padding:2px 10px;
                                 border-radius:12px;font-size:12px;margin-left:8px;">
                        {lead.status.value}
                    </span>
                    {"<span style='background:#27ae6022;color:#27ae60;padding:2px 10px;"
                     "border-radius:12px;font-size:12px;margin-left:4px;'>Scout Fee Eligible</span>"
                     if lead.scout_fee_eligible else ""}
                </div>
                <small style="color:#888;">{lead.submitted_at[:10]}</small>
            </div>
            <div style="color:#bbb;margin-top:6px;">
                {lead.governorate} — {lead.region_city}
                {(" | " + f"{lead.estimated_area_sqm:,} m²") if lead.estimated_area_sqm else ""}
                {f" | {lead.estimated_price_per_sqm_egp:,.0f} EGP/m²" if lead.estimated_price_per_sqm_egp else ""}
                {est_price}
            </div>
            <div style="color:#aaa;font-size:12px;margin-top:4px;">
                Scout: <b>{lead.scout_name}</b> ({lead.scout_id})
                {f" | Usage: {lead.allowed_usage}" if lead.allowed_usage else ""}
            </div>
            <div style="display:flex;gap:16px;margin-top:6px;font-size:12px;">
                <span style="color:{'#27ae60' if lead.legal_document_uploaded else '#e74c3c'};">
                    Documents: {'Uploaded' if lead.legal_document_uploaded else 'Pending'}
                </span>
                <span style="color:{'#27ae60' if lead.verified_by_notary else '#e74c3c'};">
                    Notary: {'Verified (Shahr Eqary)' if lead.verified_by_notary else 'Pending'}
                    {f' — Ref: {lead.notary_reference_number}' if lead.notary_reference_number else ''}
                </span>
            </div>
            {"<div style='color:#999;font-size:12px;margin-top:6px;'>" + lead.description[:200] + "</div>"
             if lead.description else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )