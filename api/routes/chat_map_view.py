"""
Smart Land Management Copilot — Chat + Map View
=================================================
The main view combining RAG chat (left 40%) and
interactive Folium map (right 60%).
"""

import streamlit as st
from streamlit_folium import st_folium

from rag.search_engine import (
    search_lands, format_context_for_llm, extract_intent,
    filter_lands_by_usage,
)
from services.glm_service import get_glm_service
from services.map_service import get_map_service
from services.prediction_service import PredictionService
from services.customer_service import CustomerServiceSystem
from services.metrics_service import get_metrics_service
from services.auction_service import CommissionCalculator
from data.land_database import get_all_lands, USAGE_COLORS


def render_chat_map_view():
    """Render the split-screen chat + map view."""

    # ── Initialize services ──
    glm = get_glm_service()
    map_svc = get_map_service()
    metrics = get_metrics_service()

    # Initialize chat history and customer service
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "cs_system" not in st.session_state:
        st.session_state["cs_system"] = CustomerServiceSystem()

    # ── Split Layout ──
    left_col, right_col = st.columns([2, 3])

    # ═══════════════════════════════════════════
    # LEFT: Chat Interface (40%)
    # ═══════════════════════════════════════════
    with left_col:
        st.markdown("#### Chat with AI Copilot")

        # Chat messages
        chat_container = st.container(height=520)
        with chat_container:
            for msg in st.session_state["chat_history"]:
                role = msg["role"]
                if role == "user":
                    st.markdown(
                        f'<div style="background:#1a3a5c;padding:10px 14px;border-radius:8px;'
                        f'margin-bottom:8px;"><b>You:</b> {msg["content"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="background:#1a1a2e;padding:10px 14px;border-radius:8px;'
                        f'margin-bottom:8px;color:#ddd;">{msg["content"]}</div>',
                        unsafe_allow_html=True,
                    )

        # Input
        user_input = st.chat_input("Ask about land investment in Egypt...")

        if user_input:
            # Add user message
            st.session_state["chat_history"].append({"role": "user", "content": user_input})

            # Create support ticket for tracking
            cs = st.session_state["cs_system"]
            ticket = cs.create_ticket(user_input, session_id="main_chat")

            # Check for escalation
            if ticket.status.value == "Escalated to Human Agent":
                with chat_container:
                    st.warning(
                        "Your query has been flagged for review by a human specialist. "
                        "You will receive a detailed response shortly. "
                        f"Ticket ID: {ticket.ticket_id}"
                    )

            # ── Route query based on intent ──
            intent = extract_intent(user_input)

            # Determine what data to retrieve
            with st.spinner("Searching land database..."):
                results = search_lands(user_input, top_k=5)
                context = format_context_for_llm(results, intent=intent)

            # Enrich context with financial/prediction data if needed
            if intent["is_financial_query"] and results:
                from services.financial_service import FinancialService
                fin_svc = FinancialService()
                fin_sections = []
                for land, score in results[:3]:
                    analysis = fin_svc.compute_full_analysis(land, investment_horizon=5)
                    fin_sections.append(
                        f"\n--- Financial Analysis: {land['Land_ID']} ---\n"
                        f"  Total Investment: {analysis.total_investment_egp:,.0f} EGP\n"
                        f"  ROI: {analysis.roi_pct}% | IRR: {analysis.irr_pct}%\n"
                        f"  Payback: {analysis.payback_years} years\n"
                        f"  NPV: {analysis.npv_egp:,.0f} EGP\n"
                        f"  Verdict: {analysis.recommendation}\n"
                        f"  Risk Flags: {', '.join(analysis.risk_flags) if analysis.risk_flags else 'None'}"
                    )
                context += "\n\n--- FINANCIAL ANALYSIS DATA ---\n" + "\n".join(fin_sections)

            if intent["is_prediction_query"] and results:
                pred_svc = PredictionService()
                pred_sections = []
                for land, score in results[:3]:
                    pred = pred_svc.predict(land, horizon_months=12)
                    pred_sections.append(
                        f"\n--- Price Prediction: {land['Land_ID']} ---\n"
                        f"  Current: {pred.current_price_per_sqm:,.0f} EGP/m\u00b2\n"
                        f"  Predicted (12mo): {pred.predicted_price_per_sqm:,.0f} EGP/m\u00b2\n"
                        f"  Change: {pred.predicted_change_pct:+.1f}% (confidence: {pred.confidence_pct}%)\n"
                        f"  Recommendation: {pred.recommendation}"
                    )
                context += "\n\n--- PRICE PREDICTION DATA ---\n" + "\n".join(pred_sections)

            if intent["is_geological_query"] and results:
                geo_sections = []
                for land, score in results[:3]:
                    geo_sections.append(
                        f"\n--- Geological Data: {land['Land_ID']} ---\n"
                        f"  Soil: {land.get('Soil_Mineral_Type', 'N/A')}\n"
                        f"  Bearing: {land.get('Bearing_Capacity_kPa', 'N/A')} kPa\n"
                        f"  Seismic: {land.get('Seismic_Risk', 'N/A')}\n"
                        f"  Groundwater: {land.get('Groundwater_Depth_m', 'N/A')}m\n"
                        f"  Water Quality: {land.get('Water_Quality', 'N/A')}\n"
                        f"  Liquefaction: {'Yes' if land.get('Liquefaction_Risk') else 'No'}\n"
                        f"  Subsidence: {'Yes' if land.get('Subsidence_Risk') else 'No'}\n"
                        f"  Flood Risk: {land.get('Flood_Risk', 'N/A')}\n"
                        f"  pH: {land.get('pH_Level', 'N/A')}\n"
                        f"  EIA Required: {'Yes' if land.get('Environmental_Permit_Required') else 'No'}"
                    )
                context += "\n\n--- GEOLOGICAL DATA ---\n" + "\n".join(geo_sections)

            if intent["is_infrastructure_query"] and results:
                infra_sections = []
                for land, score in results[:3]:
                    infra_sections.append(
                        f"\n--- Infrastructure: {land['Land_ID']} ---\n"
                        f"  Power: {land.get('Electricity_Capacity_MW', 'N/A')} MW\n"
                        f"  Water: {land.get('Daily_Water_Capacity_m3', 0):,.0f} m\u00b3/day\n"
                        f"  Gas: {'Yes' if land.get('Gas_Pipeline') else 'No'} "
                        f"({land.get('Gas_Pressure_Bar', 'N/A')} bar)\n"
                        f"  Fiber: {'Yes' if land.get('Fiber_Optic') else 'No'}\n"
                        f"  Sewage: {'Yes' if land.get('Sewage_Connection') else 'No'}\n"
                        f"  Airport: {land.get('Nearest_Airport_km', 'N/A')} km\n"
                        f"  Port: {land.get('Nearest_Port_km', 'N/A')} km\n"
                        f"  Railway: {'Yes' if land.get('Railway_Access') else 'No'}\n"
                        f"  Roads: {land.get('Road_Network_Quality', 'N/A')}"
                    )
                context += "\n\n--- INFRASTRUCTURE DATA ---\n" + "\n".join(infra_sections)

            # Stream AI response
            with chat_container:
                st.markdown(
                    '<div style="background:#1a1a2e;padding:10px 14px;border-radius:8px;margin-bottom:8px;color:#ddd;">',
                    unsafe_allow_html=True,
                )
                response_text = ""
                for chunk in glm.stream_chat(user_input, context):
                    response_text += chunk
                    st.write_stream(chunk)
                st.markdown("</div>", unsafe_allow_html=True)

            st.session_state["chat_history"].append({"role": "assistant", "content": response_text})

            # Resolve ticket
            cs.resolve_ticket(ticket.ticket_id, f"AI response provided: {response_text[:200]}")

            # Update map with search results
            if results:
                st.session_state["map_lands"] = [land for land, score in results]

            # Satisfaction survey trigger
            if cs.should_show_satisfaction_survey("main_chat"):
                with st.sidebar:
                    score = st.radio("How satisfied are you?", [1, 2, 3, 4, 5], format_func=lambda x: f"{x}/5")
                    if st.button("Submit Feedback"):
                        cs.record_satisfaction(ticket.ticket_id, score)
                        st.success("Thank you for your feedback!")

    # ═══════════════════════════════════════════
    # RIGHT: Interactive Map (60%)
    # ═══════════════════════════════════════════
    with right_col:
        st.markdown("#### Interactive Map")

        # Map controls
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns(3)

        with ctrl_col1:
            usage_filter = st.selectbox(
                "Filter by Usage",
                ["All"] + sorted(USAGE_COLORS.keys()),
                key="map_usage_filter",
            )
        with ctrl_col2:
            show_geo = st.checkbox("Geological", value=False, key="map_show_geo")
        with ctrl_col3:
            show_infra = st.checkbox("Infrastructure", value=False, key="map_show_infra")

        # Get lands for map
        map_lands = st.session_state.get("map_lands", filter_lands_by_usage(usage_filter))

        if not map_lands:
            map_lands = filter_lands_by_usage(usage_filter)

        # Build map
        fmap = map_svc.create_base_map()
        fmap = map_svc.add_land_markers(
            fmap, map_lands,
            show_geological=show_geo,
            show_infrastructure=show_infra,
        )

        # Render map
        map_data = st_folium(fmap, width="100%", height=550, key="main_map")

        # Handle click
        if map_data and map_data.get("last_clicked"):
            clicked = map_data["last_clicked"]
            if clicked.get("lat") and clicked.get("lng"):
                nearest = map_svc.find_nearest_land(
                    clicked["lat"], clicked["lng"], get_all_lands(),
                )
                if nearest:
                    st.session_state["selected_land"] = nearest
                    st.rerun()

        # Show selected land details
        if "selected_land" in st.session_state:
            land = st.session_state["selected_land"]
            with st.expander(f"Details: {land['Land_ID']}", expanded=True):
                from ui.components import render_land_card, render_financial_breakdown_table
                render_land_card(land)

                # Show transparent Financial Breakdown Table
                breakdown = CommissionCalculator.compute_for_direct_sale(
                    land,
                    scout_name=land.get("scout_name", ""),
                    scout_eligible=land.get("scout_fee_eligible", False),
                )
                st.markdown("##### Transparent Financial Breakdown")
                render_financial_breakdown_table(breakdown)