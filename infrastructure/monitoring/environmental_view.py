"""
Smart Land Management Copilot — Environmental & Creator Proximity View
======================================================================
Greenery Density Index and Content Creator Studio Suitability Score
visualizations and detailed breakdowns.
"""

import streamlit as st
import pandas as pd

from data.land_database import get_all_lands
from services.environmental_service import get_environmental_service
from ui.components import render_section_header, render_metric_card, render_progress_bar


def render_environmental_view():
    """Render the Environmental & Creator Proximity analytics view."""
    env_svc = get_environmental_service()
    lands = get_all_lands()

    render_section_header(
        "Environmental & Creator Proximity Engine",
        subtitle="Greenery Density Index (ارض خضراء وحدائق) and Content Creator Studio Suitability Score",
    )

    # Run batch analysis
    all_results = env_svc.analyze_all(lands)

    # ── Aggregate Metrics ──
    greenery_scores = []
    creator_scores = []
    for env_data in all_results.values():
        if env_data.greenery:
            greenery_scores.append(env_data.greenery.greenery_density_index)
        if env_data.creator_studio:
            creator_scores.append(env_data.creator_studio.suitability_score)

    avg_greenery = sum(greenery_scores) / max(len(greenery_scores), 1)
    avg_creator = sum(creator_scores) / max(len(creator_scores), 1)
    high_greenery = sum(1 for s in greenery_scores if s >= 60)
    high_creator = sum(1 for s in creator_scores if s >= 60)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_metric_card("Avg Greenery Index", f"{avg_greenery:.1f}/100", color="#27ae60")
    with m2:
        render_metric_card("High Greenery Lands", str(high_greenery), color="#2ecc71", delta=f"out of {len(greenery_scores)}")
    with m3:
        render_metric_card("Avg Creator Score", f"{avg_creator:.1f}/100", color="#9b59b6")
    with m4:
        render_metric_card("Studio-Suitable", str(high_creator), color="#8e44ad", delta=f"out of {len(creator_scores)}")

    st.markdown("---")

    sub_tabs = st.tabs([
        "Greenery Density Index",
        "Creator Studio Suitability",
        "Combined Analysis Table",
    ])

    # ── TAB 1: GREENERY DENSITY INDEX ──
    with sub_tabs[0]:
        st.markdown(
            '<div style="background:#1a1a2e;border:1px solid #27ae60;padding:12px;'
            'border-radius:8px;margin-bottom:16px;">'
            '<span style="color:#27ae60;font-weight:600;">Greenery Density Index</span> — '
            'Analyzes proximity to public parks and green spaces '
            '(ارض خضراء وحدائق) for corporate wellness, residential appeal, '
            'and mental peace. Score: 0-100.</div>',
            unsafe_allow_html=True,
        )

        land_options = {
            f"{l['Land_ID']} — {l['Region_City']} ({l['Allowed_Usage']})": l["Land_ID"]
            for l in lands
        }
        selected_key = st.selectbox("Select Land", list(land_options.keys()), key="env_greenery_land")
        selected_land_id = land_options[selected_key]

        env_data = all_results.get(selected_land_id)
        if not env_data or not env_data.greenery:
            st.info("No greenery data available for this land.")
            return

        g = env_data.greenery

        # Score visualization
        render_progress_bar(g.greenery_density_index, label="Greenery Density Index", color="#27ae60")

        # Detail cards
        gc1, gc2, gc3, gc4 = st.columns(4)
        with gc1:
            render_metric_card("Nearest Park", g.nearest_park_name or "N/A", color="#27ae60")
        with gc2:
            render_metric_card("Distance to Park", f"{g.nearest_park_distance_km} km", color="#2ecc71")
        with gc3:
            render_metric_card("Parks within 2km", str(g.parks_within_2km), color="#1abc9c")
        with gc4:
            render_metric_card("Parks within 5km", str(g.parks_within_5km), color="#16a085")

        gc5, gc6 = st.columns(2)
        with gc5:
            render_metric_card("Total Green Area (5km)", f"{g.total_green_area_hectares} ha", color="#27ae60")
        with gc6:
            render_metric_card("Verdict", g.greenery_verdict[:60] + "..." if len(g.greenery_verdict) > 60 else g.greenery_verdict, color="#27ae60")

    # ── TAB 2: CREATOR STUDIO SUITABILITY ──
    with sub_tabs[1]:
        st.markdown(
            '<div style="background:#1a1a2e;border:1px solid #9b59b6;padding:12px;'
            'border-radius:8px;margin-bottom:16px;">'
            '<span style="color:#9b59b6;font-weight:600;">Content Creator Studio Suitability (0-100)</span> — '
            'Engineering suitability for digital production studios, 3D graphics agencies, '
            'and YouTube creators. Weighs: <b>Ultra-low ambient noise / high greenery</b> '
            '(max 50 pts) + <b>Fiber Optic infrastructure (ألياف ضوئية)</b> (max 50 pts).</div>',
            unsafe_allow_html=True,
        )

        sel_creator_key = st.selectbox("Select Land", list(land_options.keys()), key="env_creator_land")
        sel_creator_id = land_options[sel_creator_key]

        env_data = all_results.get(sel_creator_id)
        if not env_data or not env_data.creator_studio:
            st.info("No creator studio data available for this land.")
            return

        c = env_data.creator_studio

        # Score visualization
        render_progress_bar(c.suitability_score, label="Creator Studio Suitability", color="#9b59b6")

        # Factor breakdown
        fc1, fc2 = st.columns(2)
        with fc1:
            st.markdown("**Greenery / Low-Noise Factor**")
            render_progress_bar(c.greenery_factor, max_val=50.0, label="Score", color="#27ae60")
            render_metric_card("Noise Level", c.noise_level_rating, color="#9b59b6")

        with fc2:
            st.markdown("**Fiber Optic Infrastructure Factor**")
            render_progress_bar(c.fiber_optic_factor, max_val=50.0, label="Score", color="#2980b9")
            render_metric_card("Fiber Available", "Yes" if c.fiber_optic_available else "No (Critical)", color="#27ae60" if c.fiber_optic_available else "#e74c3c")
            render_metric_card("Internet Speed", f"{c.internet_speed_mbps} Mbps", color="#2980b9")

        render_metric_card("Power Stability", c.power_stability_rating, color="#f39c12")
        render_metric_card("Verdict", c.suitability_verdict, color="#9b59b6")

    # ── TAB 3: COMBINED ANALYSIS TABLE ──
    with sub_tabs[2]:
        st.markdown("**All Lands — Environmental & Creator Proximity Summary**")
        rows = []
        for land in lands:
            lid = land["Land_ID"]
            env_data = all_results.get(lid)
            if not env_data:
                continue

            g = env_data.greenery
            c = env_data.creator_studio

            row = {
                "Land ID": lid,
                "Region": land["Region_City"],
                "Usage": land["Allowed_Usage"],
            }

            if g:
                row["Greenery Index"] = g.greenery_density_index
                row["Nearest Park"] = g.nearest_park_name
                row["Park Distance (km)"] = g.nearest_park_distance_km
                row["Parks (5km)"] = g.parks_within_5km
            else:
                row["Greenery Index"] = 0
                row["Nearest Park"] = "N/A"
                row["Park Distance (km)"] = 999
                row["Parks (5km)"] = 0

            if c:
                row["Creator Score"] = c.suitability_score
                row["Fiber Optic"] = "Yes" if c.fiber_optic_available else "No"
                row["Speed (Mbps)"] = c.internet_speed_mbps
                row["Noise Level"] = c.noise_level_rating
            else:
                row["Creator Score"] = 0
                row["Fiber Optic"] = "N/A"
                row["Speed (Mbps)"] = 0
                row["Noise Level"] = "N/A"

            rows.append(row)

        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)