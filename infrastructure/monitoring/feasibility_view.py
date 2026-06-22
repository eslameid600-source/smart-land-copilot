"""
Smart Land Management Copilot — Feasibility Report View
=========================================================
Full feasibility study with financials, predictions, risks,
and AI-generated analysis.
"""

import pandas as pd
import streamlit as st

from data.land_database import get_all_lands
from services.feasibility_service import FeasibilityReportService
from services.glm_service import get_glm_service
from ui.components import (render_cash_flow_table, render_metric_card,
                           render_section_header)


def render_feasibility_view():
    """Render the full feasibility report tab."""
    render_section_header(
        "Full Feasibility Study",
        subtitle="Comprehensive investment analysis with financials, market position, risks, and timeline",
    )

    lands = get_all_lands()
    land_options = {f"{ld['Land_ID']} — {ld['Region_City']} ({ld['Allowed_Usage']})": ld for ld in lands}
    selected = st.selectbox("Select Land for Feasibility Study", list(land_options.keys()))
    land = land_options[selected]

    horizon = st.slider("Investment Horizon (years)", 1, 20, 5, key="feas_horizon")

    # ── Generate Report ──
    if st.button("Generate Full Feasibility Report", type="primary", key="gen_feas_btn"):
        report_svc = FeasibilityReportService()
        report = report_svc.generate_report(land, investment_horizon=horizon)
        st.session_state["feasibility_report"] = report
        st.session_state["feasibility_land"] = land

    if "feasibility_report" not in st.session_state:
        st.info("Select a land and click 'Generate Full Feasibility Report' to begin.")
        return

    report = st.session_state["feasibility_report"]
    f = report["financial"]
    p = report["prediction"]
    risks = report["risk_assessment"]
    market = report["market_position"]

    # ── Executive Summary ──
    st.markdown("#### Executive Summary")
    st.markdown(report["executive_summary"])

    # ── Key Metrics ──
    mc = "#27ae60" if "STRONG" in f.recommendation or "BUY" in f.recommendation else "#f39c12"
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        render_metric_card("Total Investment", f"{f.total_investment_egp:,.0f} EGP")
    with c2:
        render_metric_card("ROI", f"{f.roi_pct}%", color=mc)
    with c3:
        render_metric_card("IRR", f"{f.irr_pct}%", color=mc)
    with c4:
        render_metric_card("Payback", f"{f.payback_years}y", color=mc)
    with c5:
        render_metric_card("NPV", f"{f.npv_egp:,.0f} EGP", color=mc)
    with c6:
        render_metric_card("Prediction", f"{p.predicted_change_pct:+.1f}%", color=mc)

    # Verdict
    st.markdown(
        f"""
        <div style="background:{mc}15;border:2px solid {mc};padding:14px;border-radius:8px;
                    text-align:center;margin:12px 0;">
            <div style="font-size:18px;font-weight:700;color:{mc};">{f.recommendation}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Financial Details ──
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Financial Details", "Price Prediction", "Risk Assessment",
        "Implementation Timeline", "AI Analysis",
    ])

    with tab1:
        st.markdown("##### Cost Breakdown")
        cost_data = {
            "Item": [
                "Land Purchase Price",
                "Registration Fee (3%)",
                "Stamp Duty (0.5%)",
                "Notary + Legal + Survey",
                "Site Preparation",
                "Development Costs",
                "TOTAL INVESTMENT",
            ],
            "Amount (EGP)": [
                f"{f.land_price_egp:,.0f}",
                f"{f.taxes.registration_fee_egp:,.0f}",
                f"{f.taxes.stamp_duty_egp:,.0f}",
                f"{f.taxes.notary_fees_egp + f.taxes.legal_review_egp + f.taxes.survey_fees_egp:,.0f}",
                f"{f.taxes.infrastructure_prep_egp:,.0f}",
                f"{f.total_development_cost_egp:,.0f}",
                f"**{f.total_investment_egp:,.0f}**",
            ],
        }
        st.dataframe(pd.DataFrame(cost_data), use_container_width=True, hide_index=True)
        st.markdown("##### Cash Flow Projection")
        render_cash_flow_table(f.cash_flows)

    with tab2:
        st.markdown("##### Price Prediction (12 Months)")
        st.markdown(
            f"- **Current Price:** {p.current_price_per_sqm:,.0f} EGP/m\u00b2\n"
            f"- **Predicted Price:** {p.predicted_price_per_sqm:,.0f} EGP/m\u00b2\n"
            f"- **Change:** {p.predicted_change_pct:+.1f}%\n"
            f"- **Confidence:** {p.confidence_pct:.0f}%"
        )
        st.markdown("**Key Drivers:**")
        for d in p.key_drivers:
            st.markdown(f"- {d}")
        st.markdown("**Risk Factors:**")
        for r in p.risk_factors:
            st.markdown(f"- {r}")

        st.markdown("##### Market Position")
        st.markdown(
            f"- **Trend:** {market['current_trend']}\n"
            f"- **1-Year Growth:** {market['price_growth_1y_pct']:+.1f}%\n"
            f"- **3-Year Growth:** {market['price_growth_3y_pct']:+.1f}%\n"
            f"- **Liquidity:** {market['liquidity']}\n"
            f"- **Avg Monthly Transactions:** {market['transaction_volume']}"
        )

    with tab3:
        st.markdown(f"##### Overall Risk Level: **{risks['overall_risk']}** ({risks['risk_count']} items)")
        for risk in risks["risk_items"]:
            sev_color = "#e74c3c" if risk["severity"] == "HIGH" else "#f39c12" if risk["severity"] == "MEDIUM" else "#27ae60"
            st.markdown(
                f"""
                <div style="background:#1a1a2e;border-left:3px solid {sev_color};
                            padding:10px 14px;border-radius:4px;margin-bottom:8px;">
                    <b>[{risk['severity']}] {risk['description']}</b><br>
                    <span style="color:#aaa;">Mitigation: {risk['mitigation']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with tab4:
        st.markdown("##### Implementation Timeline")
        for phase in report["timeline"]:
            st.markdown(
                f"""
                <div style="background:#1a1a2e;padding:10px 14px;border-radius:4px;margin-bottom:6px;">
                    <b>Phase {phase['phase']}: {phase['name']}</b>
                    <span style="float:right;color:#2980b9;">{phase['duration']}</span><br>
                    <small style="color:#aaa;">{phase['description']}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with tab5:
        st.markdown("##### AI-Powered Analysis")
        if st.button("Generate AI Commentary", key="feas_ai_btn"):
            report_svc = FeasibilityReportService()
            report_text = report_svc.format_report_for_llm(report)
            glm = get_glm_service()
            st.write_stream(
                glm.stream_feasibility(
                    report_text,
                    "Analyze this feasibility report and provide your investment recommendation "
                    "with specific action items for the investor.",
                )
            )