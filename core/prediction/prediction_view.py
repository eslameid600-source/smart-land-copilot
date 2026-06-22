"""
Smart Land Management Copilot — Prediction & Recommendations View
===================================================================
Price predictions, heatmap, and dynamic recommendations.
"""

import pandas as pd
import streamlit as st
from data.land_database import get_all_lands
from streamlit_folium import st_folium

from services.map_service import get_map_service
from services.prediction_service import PredictionService
from services.recommendation_service import RecommendationEngine
from ui.components import render_metric_card, render_section_header


def render_prediction_view():
    """Render the price prediction and recommendations tab."""
    render_section_header(
        "Price Predictions & Market Recommendations",
        subtitle="ML-based price forecasting, market trends, and actionable investment signals",
    )

    pred_svc = PredictionService()
    rec_engine = RecommendationEngine(pred_svc)
    lands = get_all_lands()

    # ── Prediction Horizon ──
    col1, col2 = st.columns(2)
    with col1:
        horizon = st.slider("Prediction Horizon (months)", 3, 36, 12, step=3)
    with col2:
        show_heatmap = st.checkbox("Show Prediction Heatmap on Map", value=True)

    # ── Generate Predictions ──
    predictions = pred_svc.predict_all(lands, horizon_months=horizon)

    # ── Summary Metrics ──
    avg_change = sum(p.predicted_change_pct for p in predictions) / len(predictions)
    avg_confidence = sum(p.confidence_pct for p in predictions) / len(predictions)
    best_pred = max(predictions, key=lambda p: p.predicted_change_pct)
    worst_pred = min(predictions, key=lambda p: p.predicted_change_pct)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_metric_card(
            "Avg Projected Change",
            f"{avg_change:+.1f}%",
            color="#27ae60" if avg_change > 0 else "#e74c3c",
        )
    with m2:
        render_metric_card("Avg Confidence", f"{avg_confidence:.0f}%")
    with m3:
        render_metric_card(
            "Best Performer",
            f"{best_pred.land_id}: {best_pred.predicted_change_pct:+.1f}%",
            color="#27ae60",
        )
    with m4:
        render_metric_card(
            "Weakest Performer",
            f"{worst_pred.land_id}: {worst_pred.predicted_change_pct:+.1f}%",
            color="#e74c3c" if worst_pred.predicted_change_pct < 0 else "#f39c12",
        )

    # ── Predictions Table ──
    st.markdown("#### Price Predictions (All Lands)")

    pred_rows = []
    for p in predictions:
        change_color = "+" if p.predicted_change_pct > 0 else ""
        pred_rows.append({
            "Land ID": p.land_id,
            "Governorate": p.governorate,
            "Current (EGP/m\u00b2)": f"{p.current_price_per_sqm:,.0f}",
            f"Predicted ({horizon}mo)": f"{p.predicted_price_per_sqm:,.0f}",
            "Change %": f"{change_color}{p.predicted_change_pct:.1f}%",
            "Confidence": f"{p.confidence_pct:.0f}%",
            "Signal": p.recommendation[:50],
        })

    df = pd.DataFrame(pred_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Heatmap Map ──
    if show_heatmap:
        st.markdown("#### Prediction Heatmap")
        heatmap_data = pred_svc.generate_heatmap_data(lands, horizon)
        map_svc = get_map_service()
        fmap = map_svc.create_base_map()
        fmap = map_svc.add_land_markers(fmap, lands, show_prediction=True, prediction_data=heatmap_data)
        fmap = map_svc.add_prediction_heatmap(fmap, heatmap_data)
        st_folium(fmap, width="100%", height=450, key="prediction_map")

    # ── Dynamic Recommendations ──
    st.markdown("#### Dynamic Market Recommendations")
    recs = rec_engine.generate_recommendations(lands, max_recommendations=5)

    for i, rec in enumerate(recs):
        urgency_colors = {
            "Buy Now": "#e74c3c",
            "Consider": "#f39c12",
            "Watch": "#2980b9",
        }
        color = urgency_colors.get(rec["urgency"], "#95a5a6")

        st.markdown(
            f"""
            <div style="background:#1a1a2e;border-left:4px solid {color};
                        padding:14px 18px;border-radius:8px;margin-bottom:10px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <b style="font-size:15px;">{rec['land_id']} — {rec['region']}</b>
                    <span style="background:{color};color:white;padding:3px 12px;
                                 border-radius:12px;font-size:12px;font-weight:700;">
                        {rec['urgency']}
                    </span>
                </div>
                <div style="color:#bbb;margin-top:4px;">
                    {rec['usage']} | Current: {rec['current_price_sqm']:,.0f} EGP/m\u00b2 |
                    6-Mo Forecast: <b style="color:{'#27ae60' if rec['predicted_change_pct'] > 0 else '#e74c3c'};">
                    +{rec['predicted_change_pct']:.1f}%</b> |
                    Confidence: {rec['confidence']:.0f}%
                </div>
                <div style="margin-top:8px;font-size:13px;color:#ccc;">
            """
            + "".join(f"<div>- {r}</div>" for r in rec["reasons"][:4])
            + f"""
                </div>
                <div style="margin-top:6px;font-size:11px;color:#888;">
                    Action Score: {rec['action_score']}/100
                    {" | AUCTION: " + rec['auction_date'] if rec['is_auction'] and rec['auction_date'] else ""}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )