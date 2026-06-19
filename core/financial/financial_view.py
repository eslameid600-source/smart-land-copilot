"""
Smart Land Management Copilot — Financial Analysis View
=========================================================
Tab showing ROI, IRR, cash flows, and cost breakdowns.
"""

import streamlit as st
import pandas as pd

from data.land_database import get_all_lands, get_land_dataframe
from services.financial_service import FinancialService
from services.glm_service import get_glm_service
import json


def _format_financial_context(analysis, land) -> str:
    """تحويل تحليل مالي ونص أرض إلى سياق نصي للـ GLM."""
    context_parts = []
    if land:
        context_parts.append(
            f"الأرض: {land.get('Land_ID', '')} — {land.get('Region_City', '')} ({land.get('Governorate', '')})\n"
            f"المساحة: {land.get('Total_Area_Sqm', 0):,} m²\n"
            f"الاستخدام: {land.get('Allowed_Usage', '')}\n"
        )
    if analysis:
        context_parts.append(json.dumps(vars(analysis) if not isinstance(analysis, dict) else analysis, default=str, ensure_ascii=False))
    return "\n".join(context_parts)
from ui.components import render_section_header, render_metric_card, render_cash_flow_table


def render_financial_view():
    """Render the financial analysis tab."""
    render_section_header(
        "Financial Analysis & Cost Calculator",
        subtitle="Full investment cost breakdown, ROI, IRR, NPV, and cash flow projections",
    )

    lands = get_all_lands()
    land_options = {f"{l['Land_ID']} — {l['Region_City']}": l for l in lands}

    # ── Land Selection ──
    selected = st.selectbox("Select Land for Analysis", list(land_options.keys()))
    land = land_options[selected]

    # ── Parameters ──
    col1, col2 = st.columns(2)
    with col1:
        horizon = st.slider("Investment Horizon (years)", 1, 20, 5)
    with col2:
        custom_discount = st.checkbox("Custom Discount Rate")
        discount = st.number_input(
            "Discount Rate (%)", min_value=1.0, max_value=50.0, value=15.0,
            step=0.5, disabled=not custom_discount,
        )

    # ── Compute Analysis ──
    fin_svc = FinancialService()
    analysis = fin_svc.compute_full_analysis(
        land,
        investment_horizon=horizon,
        discount_rate=discount / 100.0 if custom_discount else None,
    )

    # ── Key Metrics Row ──
    st.markdown("#### Key Financial Metrics")

    # Color based on verdict
    if "STRONG" in analysis.recommendation:
        mc = "#27ae60"
    elif "BUY" in analysis.recommendation:
        mc = "#2980b9"
    elif "HOLD" in analysis.recommendation:
        mc = "#f39c12"
    else:
        mc = "#e74c3c"

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        render_metric_card("Total Investment", f"{analysis.total_investment_egp:,.0f} EGP")
    with m2:
        render_metric_card("ROI", f"{analysis.roi_pct}%", color=mc)
    with m3:
        render_metric_card("IRR", f"{analysis.irr_pct}%", color=mc)
    with m4:
        render_metric_card("Payback", f"{analysis.payback_years} years", color=mc)
    with m5:
        render_metric_card("NPV", f"{analysis.npv_egp:,.0f} EGP", color=mc)

    # ── Verdict Banner ──
    st.markdown(
        f"""
        <div style="background:{mc}15;border:2px solid {mc};padding:16px;border-radius:8px;
                    text-align:center;margin:16px 0;">
            <div style="font-size:12px;color:#888;text-transform:uppercase;">Investment Verdict</div>
            <div style="font-size:20px;font-weight:700;color:{mc};margin-top:6px;">
                {analysis.recommendation}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Risk Flags ──
    if analysis.risk_flags:
        st.markdown("#### Risk Flags")
        for flag in analysis.risk_flags:
            st.warning(flag)

    # ── Tax & Fee Breakdown ──
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### Tax & Acquisition Costs")
        tax_data = {
            "Item": [
                "Land Registration Fee (3%)",
                "Stamp Duty (0.5%)",
                "Notary Public Fees",
                "Legal Review Fees",
                "Land Survey Fees",
                "Infrastructure Preparation",
            ],
            "Amount (EGP)": [
                f"{analysis.taxes.registration_fee_egp:,.0f}",
                f"{analysis.taxes.stamp_duty_egp:,.0f}",
                f"{analysis.taxes.notary_fees_egp:,.0f}",
                f"{analysis.taxes.legal_review_egp:,.0f}",
                f"{analysis.taxes.survey_fees_egp:,.0f}",
                f"{analysis.taxes.infrastructure_prep_egp:,.0f}",
            ],
        }
        st.dataframe(pd.DataFrame(tax_data), use_container_width=True, hide_index=True)
        st.caption(
            f"Total Acquisition Costs: **{analysis.taxes.total_acquisition_cost_egp:,.0f} EGP** | "
            f"All-In Cost: **{analysis.taxes.total_all_in_cost_egp:,.0f} EGP**"
        )

    with col_b:
        st.markdown("#### Revenue Summary")
        rev_data = {
            "Metric": [
                "Land Price",
                "Development Cost",
                "Total Investment",
                "Annual Revenue",
                "Annual OpEx",
                "Annual Net Income",
                "Profit Margin",
            ],
            "Value": [
                f"{analysis.land_price_egp:,.0f} EGP",
                f"{analysis.total_development_cost_egp:,.0f} EGP",
                f"{analysis.total_investment_egp:,.0f} EGP",
                f"{analysis.annual_revenue_egp:,.0f} EGP",
                f"{analysis.annual_operating_cost_egp:,.0f} EGP",
                f"{analysis.annual_net_income_egp:,.0f} EGP",
                f"{analysis.profit_margin_pct}%",
            ],
        }
        st.dataframe(pd.DataFrame(rev_data), use_container_width=True, hide_index=True)

    # ── Cash Flow Table ──
    st.markdown("#### Cash Flow Projection")
    render_cash_flow_table(analysis.cash_flows)

    # ── AI Analysis ──
    st.markdown("#### AI Financial Analysis")
    if st.button("Generate AI Financial Commentary", key="fin_ai_btn"):
        report_text = _format_financial_context(analysis, land)
        glm = get_glm_service()
        response = st.write_stream(
            glm.stream_feasibility(report_text, "Provide a detailed financial analysis and investment recommendation.")
        )