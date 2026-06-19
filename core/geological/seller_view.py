"""
Smart Land Management Copilot — Seller/Owner View
==================================================
Property registration interface (تسجيل أملاك) for Sale, Rent,
or Portfolio Tracking with transparent Financial Cleared Matrix.
"""

import streamlit as st
import pandas as pd

from data.land_database import get_all_lands, USAGE_COLORS
from services.auction_service import get_auction_engine, CommissionCalculator
from services.user_service import get_user_service
from services.broker_delegation_service import get_broker_delegation_service
from ui.components import render_section_header, render_metric_card


def render_seller_view():
    """
    Render the Seller/Owner dashboard with property registration,
    financial cleared matrix, and broker delegation management.
    """
    user_svc = get_user_service()
    auction_engine = get_auction_engine()
    delegation_svc = get_broker_delegation_service()

    current_user = _get_current_seller(user_svc)
    if not current_user:
        st.warning("No Seller/Owner account selected. Please log in from the account panel.")
        return

    render_section_header(
        f"Property Management — {current_user.full_name}",
        subtitle="Register properties, view financial breakdowns, and manage broker delegations",
    )

    lands = get_all_lands()

    # ── Seller Metrics ──
    owned_ids = current_user.owned_land_ids
    owned_lands = [l for l in lands if l["Land_ID"] in owned_ids]
    total_value = sum(l["Total_Area_Sqm"] * l["Price_Per_Sqm_EGP"] for l in owned_lands)

    m1, m2, m3 = st.columns(3)
    with m1:
        render_metric_card("Listed Properties", str(len(owned_lands)), color="#2980b9")
    with m2:
        render_metric_card("Total Portfolio Value", f"{total_value:,.0f} EGP", color="#27ae60")
    with m3:
        render_metric_card("Delegated Brokers", str(len(_get_all_delegations(owned_ids, delegation_svc))), color="#f39c12")

    st.markdown("---")

    # ── Tabs ──
    sub_tabs = st.tabs([
        "Register Property (تسجيل أملاك)",
        "Financial Cleared Matrix",
        "Broker Delegation",
        "My Listings",
    ])

    # ── TAB 1: PROPERTY REGISTRATION ──
    with sub_tabs[0]:
        st.markdown(
            '<div style="background:#1a1a2e;border:1px solid #2980b9;padding:12px;'
            'border-radius:8px;margin-bottom:16px;">'
            '<span style="color:#2980b9;font-weight:600;">تسجيل أملاك</span> — '
            'Register a new property or manage an existing listing for '
            '<b>Sale</b>, <b>Rent</b>, or <b>Portfolio Tracking</b>.</div>',
            unsafe_allow_html=True,
        )

        with st.form("register_property_form"):
            rc1, rc2 = st.columns(2)
            with rc1:
                sel_land_key = st.selectbox(
                    "Select Land to Register",
                    [f"{l['Land_ID']} — {l['Region_City']} ({l['Allowed_Usage']})" for l in lands],
                    key="seller_reg_land",
                )
                listing_intent = st.selectbox(
                    "Listing Intent",
                    ["Sale", "Rent", "Portfolio Tracking"],
                    key="seller_intent",
                )
            with rc2:
                rental_price = st.number_input(
                    "Monthly Rent (EGP, if Rent)",
                    min_value=0, value=0, step=1000,
                    key="seller_rental",
                )
                marketing_notes = st.text_area(
                    "Marketing Notes (optional)",
                    key="seller_notes",
                )

            if st.form_submit_button("Register Property", type="primary"):
                land_id = sel_land_key.split(" — ")[0]
                user_svc.register_owned_land(current_user.user_id, land_id)
                st.success(f"Property {land_id} registered as '{listing_intent}'")
                st.rerun()

    # ── TAB 2: FINANCIAL CLEARED MATRIX ──
    with sub_tabs[1]:
        st.markdown(
            '<div style="background:#1a1a2e;border:1px solid #27ae60;padding:12px;'
            'border-radius:8px;margin-bottom:16px;">'
            '<span style="color:#27ae60;font-weight:600;">Transparent Fee Clearing</span> — '
            'Every party\'s exact financial cut from the transaction, '
            'including Real Estate Disposal Tax '
            '(\u0636\u0631\u064a\u0628\u0629 \u0627\u0644\u062a\u0635\u0631\u0641\u0627\u062a \u0627\u0644\u0639\u0642\u0627\u0631\u064a\u0629) at 2.5%, '
            'Shahr Eqary registration fees, and stamp duty.</div>',
            unsafe_allow_html=True,
        )

        display_lands = owned_lands if owned_lands else lands
        land_options = {
            f"{l['Land_ID']} — {l['Region_City']} ({l['Allowed_Usage']}) [{l['Investment_Status']}]": l
            for l in display_lands
        }
        selected_key = st.selectbox("Select Land", list(land_options.keys()), key="seller_fee_land")
        land = land_options[selected_key]

        # Determine sale value
        auction = auction_engine.get_auction_by_land(land["Land_ID"])
        if auction and auction.current_highest_bid_egp > 0:
            sale_value = auction.current_highest_bid_egp
            value_label = f"Current Highest Bid: {sale_value:,.0f} EGP"
        elif land["Investment_Status"] == "Public Auction" and land.get("Starting_Price_Per_Sqm_EGP"):
            sale_value = land["Starting_Price_Per_Sqm_EGP"] * land["Total_Area_Sqm"]
            value_label = f"Starting Price Total: {sale_value:,.0f} EGP"
        else:
            sale_value = land["Total_Area_Sqm"] * land["Price_Per_Sqm_EGP"]
            value_label = f"Direct Sale Price: {sale_value:,.0f} EGP"

        st.markdown(f"**{land['Land_ID']}** — {value_label}")

        breakdown = CommissionCalculator.compute_breakdown(
            total_value_egp=sale_value,
            land_id=land["Land_ID"],
            auction_id=auction.auction_id if auction else None,
            is_auction=land["Investment_Status"] == "Public Auction",
        )

        rows = CommissionCalculator.format_breakdown_table(breakdown)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

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

    # ── TAB 3: BROKER DELEGATION ──
    with sub_tabs[2]:
        st.markdown(
            '<div style="background:#1a1a2e;border:1px solid #f39c12;padding:12px;'
            'border-radius:8px;margin-bottom:16px;">'
            '<span style="color:#f39c12;font-weight:600;">Dual-Broker Delegation</span> — '
            'Delegate a maximum of 2 verified brokers per land. '
            'Only the broker who closes the deal earns the commission (Winner-Takes-Commission Rule).</div>',
            unsafe_allow_html=True,
        )

        display_lands = owned_lands if owned_lands else lands
        del_land_options = {
            f"{l['Land_ID']} — {l['Region_City']}": l["Land_ID"]
            for l in display_lands
        }
        selected_del_key = st.selectbox("Select Land", list(del_land_options.keys()), key="del_land_sel")
        selected_land_id = del_land_options[selected_del_key]

        # Show current allocations
        allocations = delegation_svc.get_land_brokers(selected_land_id)
        if allocations:
            st.markdown(f"**Current Allocations ({len(allocations)}/2):**")
            for alloc in allocations:
                win_badge = (
                    ' <span style="background:#27ae6020;color:#27ae60;padding:2px 8px;'
                    'border-radius:8px;font-size:11px;">WINNER</span>'
                    if alloc.is_winning_broker else ""
                )
                st.markdown(
                    f"""
                    <div style="background:#1a1a2e;border-left:3px solid #f39c12;
                                padding:10px 14px;border-radius:4px;margin-bottom:6px;">
                        <b>{alloc.broker_name}</b> ({alloc.broker_id}){win_badge}<br>
                        <small>Leads: {alloc.leads_generated} | Deals: {alloc.deals_closed} |
                        Commission: {alloc.commission_earned_egp:,.0f} EGP</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No brokers allocated to this land.")

        # Allocate broker form
        if len(allocations) < 2:
            verified_brokers = user_svc.list_users()
            verified_brokers = [
                u for u in verified_brokers
                if u.role.value == "Certified Broker" and u.is_broker_verified
            ]
            if verified_brokers:
                with st.form("allocate_broker_form"):
                    broker_options = {f"{b.full_name} ({b.user_id})": b for b in verified_brokers}
                    sel_broker = st.selectbox("Select Verified Broker", list(broker_options.keys()), key="alloc_broker_sel")
                    if st.form_submit_button("Allocate Broker", type="primary"):
                        broker = broker_options[sel_broker]
                        alloc, error = delegation_svc.allocate_broker(
                            land_id=selected_land_id,
                            broker_id=broker.user_id,
                            broker_name=broker.full_name,
                        )
                        if error:
                            st.error(error)
                        else:
                            st.success(f"Broker {broker.full_name} allocated to {selected_land_id}")
                            st.rerun()
            else:
                st.info("No verified brokers available.")
        else:
            st.warning("Maximum 2 brokers already allocated. Remove one before adding another.")

    # ── TAB 4: MY LISTINGS ──
    with sub_tabs[3]:
        if not owned_lands:
            st.info("No properties registered yet. Use the Register Property tab to get started.")
        else:
            for land in owned_lands:
                total = land["Total_Area_Sqm"] * land["Price_Per_Sqm_EGP"]
                color = USAGE_COLORS.get(land["Allowed_Usage"], "#95a5a6")
                st.markdown(
                    f"""
                    <div style="background:#1a1a2e;border-left:4px solid {color};
                                padding:16px;border-radius:8px;margin-bottom:12px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <b style="color:{color};">{land['Land_ID']}</b>
                            <span style="background:{color}22;color:{color};padding:2px 10px;
                                         border-radius:12px;font-size:12px;">{land['Allowed_Usage']}</span>
                        </div>
                        <div style="color:#bbb;margin-top:6px;">{land['Governorate']} — {land['Region_City']}</div>
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px;">
                            <div><small style="color:#888;">Area</small><br><b>{land['Total_Area_Sqm']:,} m\u00b2</b></div>
                            <div><small style="color:#888;">Price/m\u00b2</small><br><b>{land['Price_Per_Sqm_EGP']:,} EGP</b></div>
                            <div><small style="color:#888;">Total Value</small><br><b>{total:,.0f} EGP</b></div>
                            <div><small style="color:#888;">Status</small><br><b>{land['Investment_Status']}</b></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def _get_current_seller(user_svc):
    uid = st.session_state.get("current_user_id")
    if not uid:
        return None
    user = user_svc.get_user(uid)
    if user and user.role.value == "Seller/Owner":
        return user
    return None


def _get_all_delegations(land_ids, delegation_svc):
    """Get all broker delegations for a list of land IDs."""
    all_allocs = []
    for lid in land_ids:
        all_allocs.extend(delegation_svc.get_land_brokers(lid))
    return all_allocs