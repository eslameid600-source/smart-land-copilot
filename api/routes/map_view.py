"""
============================================================
Smart Land Management Copilot — Map View
============================================================
Renders the interactive Folium map with click handling.

Design Pattern: View (MVP)
SOLID: SRP — map rendering and interaction only
============================================================
"""

from __future__ import annotations

import streamlit as st
from streamlit_folium import st_folium

from services.state_manager import get_state
from services.map_service import get_map_service


def render_map_view() -> None:
    """
    Render the interactive Folium map (right panel, 60% width).

    Handles map clicks and auto-generates chat queries.
    """
    state = get_state()
    map_service = get_map_service()

    # Build map with current filter and highlight
    folium_map = map_service.build_map(
        usage_filter=state.map.selected_usage_filter,
        highlight_land_id=state.map.highlighted_land_id,
    )

    # Render map
    st.subheader("Egypt Land Map")
    map_data = st_folium(
        folium_map,
        width="100%",
        height=680,
        returned_objects=["last_clicked"],
        key="main_folium_map",
    )

    # Handle map click
    _handle_map_click(map_data, state)


def _handle_map_click(map_data: dict, state) -> None:
    """
    Process map click events.

    When a user clicks the map, find the nearest land and
    auto-generate a chat query about it.
    """
    if not map_data or "last_clicked" not in map_data:
        return

    clicked = map_data["last_clicked"]
    if not clicked:
        return

    lat = clicked.get("lat")
    lng = clicked.get("lng")
    if lat is None or lng is None:
        return

    map_service = get_map_service()
    nearest = map_service.find_nearest_land(lat, lng, max_distance_deg=1.0)

    if nearest:
        land_id = nearest["Land_ID"]
        region = nearest["Region_City"]
        usage = nearest["Allowed_Usage"]
        gov = nearest["Governorate"]

        auto_query = f"Tell me about {land_id} in {region}, {gov} — {usage} land"
        state.chat.auto_query_from_map = auto_query
        state.map.set_highlight(land_id)

        st.toast(f"Selected: {land_id} — {region}", icon="📍")