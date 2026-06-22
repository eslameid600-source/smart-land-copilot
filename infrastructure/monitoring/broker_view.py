"""
Smart Land Management Copilot — Broker Dashboard View
======================================================
Certified broker dashboard with listing management,
performance metrics, and commission tracking.

Brokers with status 'Pending Verification' are blocked from
accessing the dashboard or managing listings.
"""

import pandas as pd
import streamlit as st

from services.auction_service import get_auction_engine
from services.broker_delegation_service import get_broker_delegation_service
from services.user_service import get_user_service
from ui.components import render_metric_card, render_section_header


def render_broker_view():
    """
    Render the Certified Broker dashboard.

    Access control:
    - If broker status is 'Pending Verification', show a blocking
      message with document submission instructions.
    - If verified, show full dashboard with listings, performance,
      and commission history.
    """
    user_svc = get_user_service()
    delegation_svc = get_broker_delegation_service()
    get_auction_engine()

    current_user = _get_current_broker(user_svc)
    if not current_user:
        st.warning("No Certified Broker account selected. Please log in from the account panel.")
        return

    # ── Access Control Gate ──
    if not current_user.is_broker_verified:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg, #e74c3c10, #e74c3c05);
                border: 2px solid #e74c3c40;
                border-radius: 12px;
                padding: 40px 24px;
                text-align: center;
                margin: 20px 0;
            ">
                <div style="font-size:48px;margin-bottom:16px;">🔒</div>
                <h3 style="color:#e74c3c;margin:0;">Account Pending Verification</h3>
                <p style="color:#bbb;margin-top:12px;max-width:500px;margin-left:auto;margin-right:auto;">
                    Your broker account requires document verification before you can
                    access the dashboard or manage listings. Please submit the required
                    documents:
                </p>
                <ul style="text-align:left;max-width:400px;margin:16px auto;color:#ccc;">
                    <li>Real Estate Brokerage License (شهادة مزاولة المهنة)</li>
                    <li>Financial Guarantees</li>
                </ul>
                <p style="color:#888;font-size:13px;">
                    Contact the platform administrator or check the account panel for verification status.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    render_section_header(
        f"Broker Dashboard — {current_user.full_name}",
        subtitle=f"License: {current_user.broker_license_number} | {', '.join(current_user.broker_specializations)}",
    )

    # ── Broker Performance Metrics ──
    perf = delegation_svc.get_broker_performance_summary(current_user.user_id)
    ledger = delegation_svc.get_all_commission_records()
    my_wins = [r for r in ledger if r.winning_broker_id == current_user.user_id]
    total_won_commission = sum(r.winning_broker_commission_egp for r in my_wins)

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        render_metric_card("Assigned Lands", str(perf["lands_assigned"]), color="#2980b9")
    with m2:
        render_metric_card("Leads Generated", str(perf["total_leads_generated"]), color="#f39c12")
    with m3:
        render_metric_card("Deals Closed", str(perf["total_deals_closed"]), color="#27ae60")
    with m4:
        render_metric_card("Win Rate", f"{perf['win_rate_pct']}%", color="#e74c3c")
    with m5:
        render_metric_card("Commission Earned", f"{total_won_commission:,.0f} EGP", color="#9b59b6")

    st.markdown("---")

    # ── Tabs ──
    sub_tabs = st.tabs([
        "My Assigned Lands",
        "Commission Ledger",
        "Performance Detail",
    ])

    # ── TAB 1: ASSIGNED LANDS ──
    with sub_tabs[0]:
        from data.land_database import get_all_lands
        lands = get_all_lands()
        land_map = {land["Land_ID"]: land for land in lands}

        assigned_ids = current_user.assigned_land_ids
        if not assigned_ids:
            st.info("No lands assigned to you yet. Sellers will delegate properties through the platform.")
        else:
            for land_id in assigned_ids:
                land = land_map.get(land_id)
                if not land:
                    continue

                allocations = delegation_svc.get_land_brokers(land_id)
                my_alloc = next((a for a in allocations if a.broker_id == current_user.user_id), None)
                other_allocs = [a for a in allocations if a.broker_id != current_user.user_id]

                color = "#2980b9"
                is_winner = my_alloc.is_winning_broker if my_alloc else False

                total = land["Total_Area_Sqm"] * land["Price_Per_Sqm_EGP"]
                other_info = ""
                if other_allocs:
                    other_info = (
                        f'<div style="margin-top:6px;font-size:12px;color:#f39c12;">'
                        f'Co-Broker: {other_allocs[0].broker_name} ({other_allocs[0].broker_id})</div>'
                    )

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
                        <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-top:12px;">
                            <div><small style="color:#888;">Area</small><br><b>{land['Total_Area_Sqm']:,} m\u00b2</b></div>
                            <div><small style="color:#888;">Price/m\u00b2</small><br><b>{land['Price_Per_Sqm_EGP']:,} EGP</b></div>
                            <div><small style="color:#888;">Total</small><br><b>{total:,.0f} EGP</b></div>
                            <div><small style="color:#888;">My Leads</small><br><b>{my_alloc.leads_generated if my_alloc else 0}</b></div>
                        </div>
                        {"<div style='margin-top:8px;color:#27ae60;font-weight:600;font-size:13px;'>"
                         "WINNING BROKER — Commission Secured</div>"
                         if is_winner else ""}
                        {other_info}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # ── TAB 2: COMMISSION LEDGER ──
    with sub_tabs[1]:
        if not ledger:
            st.info("No commission records yet.")
        else:
            rows = []
            for record in ledger:
                rows.append({
                    "Land ID": record.land_id,
                    "Transaction (EGP)": f"{record.transaction_value_egp:,.0f}",
                    "Commission %": f"{record.broker_commission_pct}%",
                    "Winning Broker": record.winning_broker_id or "N/A",
                    "Winning Commission (EGP)": f"{record.winning_broker_commission_egp:,.0f}",
                    "Secondary Broker": record.secondary_broker_id or "N/A",
                    "Secondary Commission (EGP)": f"{record.secondary_broker_commission_egp:,.0f}",
                    "Deal Closed": "Yes" if record.deal_closed else "No",
                    "Closed Date": (record.closed_date[:10] if record.closed_date else ""),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── TAB 3: PERFORMANCE DETAIL ──
    with sub_tabs[2]:
        st.markdown("### Performance Summary")
        st.json({
            "broker_id": perf["broker_id"],
            "lands_assigned": perf["lands_assigned"],
            "total_leads_generated": perf["total_leads_generated"],
            "total_deals_closed": perf["total_deals_closed"],
            "lands_won": perf["lands_won"],
            "win_rate_pct": perf["win_rate_pct"],
            "total_commission_earned_egp": perf["total_commission_earned_egp"],
        })


def _get_current_broker(user_svc):
    uid = st.session_state.get("current_user_id")
    if not uid:
        return None
    user = user_svc.get_user(uid)
    if user and user.role.value == "Certified Broker":
        return user
    return None