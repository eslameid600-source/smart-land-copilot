"""
============================================================
Smart Land Management Copilot — Map Service
============================================================
Map rendering and interaction service.

Features:
  - Folium map generation with configurable tiles
  - Circle markers with usage-based coloring
  - Rich HTML popups with land details
  - Marker clustering support
  - Map caching to avoid re-rendering
  - Spatial nearest-land lookup

Design Pattern: Builder (map construction), Cache (map instances)
SOLID:
  - SRP: Map rendering only
  - DIP: Depends on repository, not raw data
============================================================
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import folium
from folium.plugins import MarkerCluster

from config.settings import AppConfig, get_settings
from data.repository import LandRepository, get_repository
from models.land import USAGE_COLORS, LandRecord

logger = logging.getLogger(__name__)


class MapService:
    """
    Service for building and caching Folium maps.

    Separates map construction from the Streamlit UI layer.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        repository: Optional[LandRepository] = None,
    ) -> None:
        self._config = config or get_settings()
        self._repo = repository or get_repository()
        self._mc = self._config.map_config
        self._cache: Dict[str, folium.Map] = {}

    def build_map(
        self,
        usage_filter: Optional[str] = None,
        highlight_land_id: Optional[str] = None,
    ) -> folium.Map:
        """
        Build a Folium map with land markers.

        Args:
            usage_filter: Only show lands of this usage type. None/All = show all.
            highlight_land_id: Add a special highlight ring around this land.

        Returns:
            A folium.Map instance ready for st_folium().
        """
        cache_key = f"{usage_filter}:{highlight_land_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        mc = self._mc

        egypt_map = folium.Map(
            location=[mc.default_center_lat, mc.default_center_lon],
            zoom_start=mc.default_zoom,
            tiles=None,
            control_scale=True,
        )

        # Dark tile layer
        folium.raster_layers.TileLayer(
            tiles=mc.tile_url,
            attr=mc.tile_attribution,
            name="Dark Mode",
            max_zoom=19,
            overlay=False,
            control=True,
        ).add_to(egypt_map)

        # Get filtered lands
        if usage_filter and usage_filter != "All":
            lands = self._repo.filter_by_usage(usage_filter)
        else:
            lands = self._repo.get_all()

        # Marker clustering
        if mc.enable_clustering and len(lands) > 3:
            cluster = MarkerCluster(
                name="Land Parcels",
                options={"maxClusterRadius": mc.cluster_radius},
            ).add_to(egypt_map)

        for land in lands:
            color = USAGE_COLORS.get(land.allowed_usage, "#95a5a6")
            popup_html = self._build_popup(land)
            self._build_label(land)

            marker = folium.CircleMarker(
                location=[land.latitude, land.longitude],
                radius=land.radius_meters / 1000,  # Convert meters to km for display
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.25,
                weight=2,
                popup=folium.Popup(popup_html, max_width=mc.popup_max_width),
                tooltip=land.land_id,
            )

            if mc.enable_clustering and len(lands) > 3:
                marker.add_to(cluster)
            else:
                marker.add_to(egypt_map)

            # Auction dashed ring
            if land.is_auction:
                folium.CircleMarker(
                    location=[land.latitude, land.longitude],
                    radius=land.radius_meters / 1000 + 0.15,
                    color="#f39c12",
                    fill=False,
                    weight=2,
                    dash_array="8, 6",
                    tooltip=f"AUCTION: {land.auction_date}",
                ).add_to(egypt_map)

            # Highlight ring
            if highlight_land_id and land.land_id == highlight_land_id:
                folium.CircleMarker(
                    location=[land.latitude, land.longitude],
                    radius=land.radius_meters / 1000 + 0.3,
                    color="#00ff88",
                    fill=False,
                    weight=3,
                    tooltip=f"Selected: {land.land_id}",
                ).add_to(egypt_map)

            # Label marker
            folium.Marker(
                location=[land.latitude + 0.15, land.longitude + 0.15],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:9px;color:{color};white-space:nowrap;'
                         f'text-shadow:1px 1px 3px #000;font-weight:bold;">{land.land_id}</div>',
                    icon_size=(80, 20),
                    icon_anchor=(0, 10),
                ),
            ).add_to(egypt_map)

        # Layer control
        folium.LayerControl().add_to(egypt_map)

        # Cache
        self._cache[cache_key] = egypt_map
        if len(self._cache) > 20:
            oldest = list(self._cache.keys())[:5]
            for k in oldest:
                del self._cache[k]

        logger.debug("Map built: %d markers, filter=%s", len(lands), usage_filter)
        return egypt_map

    def find_nearest_land(
        self, lat: float, lon: float, max_distance_deg: float = 1.0
    ) -> Optional[Dict[str, Any]]:
        """Find the nearest land to a clicked coordinate."""
        record = self._repo.find_nearest(lat, lon, max_distance_deg)
        return record.to_dict() if record else None

    def clear_cache(self) -> None:
        """Clear the map cache."""
        self._cache.clear()

    # ----------------------------------------------------------
    # Popup & Label Builders
    # ----------------------------------------------------------

    @staticmethod
    def _build_popup(land: LandRecord) -> str:
        """Build rich HTML popup for a land marker."""
        status_badge = (
            '<span style="background:#f39c12;color:#000;padding:2px 8px;'
            'border-radius:10px;font-weight:bold;font-size:11px;">AUCTION</span>'
            if land.is_auction
            else '<span style="background:#27ae60;color:#fff;padding:2px 8px;'
                 'border-radius:10px;font-weight:bold;font-size:11px;">DIRECT SALE</span>'
        )

        auction_block = ""
        if land.is_auction:
            auction_block = (
                f"<tr><td><b>Auction Date</b></td><td>{land.auction_date or 'N/A'}</td></tr>"
                f"<tr><td><b>Starting Price</b></td><td>{land.starting_price_per_sqm_egp:,} EGP/m2</td></tr>"
            )

        return f"""
        <div style="font-family:Inter,sans-serif;min-width:250px;">
            <table style="width:100%;font-size:13px;border-collapse:collapse;">
                <tr>
                    <td colspan="2" style="text-align:center;padding-bottom:8px;">
                        <b style="font-size:15px;color:#ecf0f1;">{land.land_id}</b><br>
                        {status_badge}
                    </td>
                </tr>
                <tr><td><b>Location</b></td><td>{land.governorate} — {land.region_city}</td></tr>
                <tr><td><b>Usage</b></td><td><b>{land.allowed_usage}</b></td></tr>
                <tr><td><b>Area</b></td><td>{land.total_area_sqm:,} sqm</td></tr>
                <tr><td><b>Price</b></td><td>{land.price_per_sqm_egp:,} EGP/m2</td></tr>
                <tr><td><b>Total</b></td><td>{land.total_price_egp:,} EGP</td></tr>
                <tr><td><b>Soil</b></td><td>{land.soil_mineral_type}</td></tr>
                <tr><td><b>Highways</b></td><td>{land.nearest_highways}</td></tr>
                <tr><td><b>Utilities</b></td><td>{land.utilities_availability}</td></tr>
                {auction_block}
                <tr><td colspan="2" style="padding-top:6px;font-size:11px;color:#aaa;">
                    {land.gov_feasibility_notes[:120]}...
                </td></tr>
            </table>
        </div>
        """

    @staticmethod
    def _build_label(land: LandRecord) -> str:
        """Build a simple text label for the map."""
        return land.land_id


# ----------------------------------------------------------
# Module-level singleton
# ----------------------------------------------------------

_map_service: Optional[MapService] = None


def get_map_service() -> MapService:
    """Get or create the global map service singleton."""
    global _map_service
    if _map_service is None:
        _map_service = MapService()
    return _map_service


def reset_map_service() -> None:
    """Reset the map service singleton (useful for testing)."""
    global _map_service
    _map_service = None