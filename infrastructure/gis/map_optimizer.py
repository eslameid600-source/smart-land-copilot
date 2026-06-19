"""
Smart Land Copilot — GIS Optimization Module
===============================================
Optimizes map rendering by replacing heavy Folium usage with
lightweight alternatives (Mapbox GL JS / Deck.gl) and
optimizing OSMnx POI fetching with radius limits.

Features:
    1. `optimize_poi_query()` — OSMnx with bounded radius
    2. `convert_to_deckgl()` — Convert GeoJSON to Deck.gl format
    3. `get_mapbox_config()` — Mapbox GL JS configuration
    4. `simplify_geojson()` — Reduce GeoJSON size for faster rendering
"""

import os
import json
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

# Maximum radius for POI queries (meters) — prevents overload
MAX_POI_RADIUS_METERS = 5000  # 5km max

# Default bounding box for Egypt (Cairo area)
EGYPT_BOUNDS = {
    "min_lat": 22.0,
    "max_lat": 31.7,
    "min_lon": 25.0,
    "max_lon": 37.0,
}

CAIRO_BOUNDS = {
    "min_lat": 29.8,
    "max_lat": 30.3,
    "min_lon": 31.1,
    "max_lon": 31.5,
}


@dataclass
class MapConfig:
    """Mapbox configuration for frontend."""
    style_url: str = "mapbox://styles/mapbox/light-v11"
    access_token: str = ""
    center_lat: float = 30.0444  # Cairo
    center_lon: float = 31.2357
    zoom: int = 10
    max_zoom: int = 18
    min_zoom: int = 5
    pitch: int = 0
    bearing: int = 0


# ──────────────────────────────────────────────
# 1. OSMnx POI Optimization
# ──────────────────────────────────────────────

def optimize_poi_query(
    lat: float,
    lon: float,
    radius_meters: float = 1000,
    poi_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Fetch POIs from OSMnx with a bounded radius.
    Falls back gracefully if OSMnx is not installed.

    Args:
        lat: Latitude of center point
        lon: Longitude of center point
        radius_meters: Search radius (capped at MAX_POI_RADIUS_METERS)
        poi_types: Types of POIs to fetch (e.g., ["school", "hospital", "bank"])

    Returns:
        dict with features list and metadata
    """
    # Cap radius to prevent overload
    radius_meters = min(radius_meters, MAX_POI_RADIUS_METERS)

    if poi_types is None:
        poi_types = ["school", "hospital", "bank", "mosque", "supermarket", "restaurant"]

    try:
        import osmnx as ox
        import networkx as nx

        # Limit the graph size
        ox.settings.max_query_area_size = radius_meters * radius_meters * 3.14 / 1_000_000
        ox.settings.log_console = False

        # Get POIs within radius
        pois = ox.features_from_point(
            center_point=(lat, lon),
            dist=radius_meters,
            tags={"amenity": poi_types},
        )

        # Convert to simplified GeoJSON
        if pois.empty:
            return {
                "type": "FeatureCollection",
                "features": [],
                "metadata": {
                    "center": {"lat": lat, "lon": lon},
                    "radius_meters": radius_meters,
                    "count": 0,
                },
            }

        # Simplify geometry to reduce size
        geojson = pois.__geo_interface__
        simplified = simplify_geojson(geojson, tolerance=0.001)

        return {
            "type": "FeatureCollection",
            "features": simplified.get("features", []),
            "metadata": {
                "center": {"lat": lat, "lon": lon},
                "radius_meters": radius_meters,
                "count": len(simplified.get("features", [])),
                "source": "osmnx",
            },
        }

    except ImportError:
        logger.warning("osmnx not installed — returning empty POI set")
        return {
            "type": "FeatureCollection",
            "features": [],
            "metadata": {
                "center": {"lat": lat, "lon": lon},
                "radius_meters": radius_meters,
                "count": 0,
                "source": "empty (osmnx unavailable)",
            },
        }
    except Exception as e:
        logger.error(f"OSMnx POI query failed: {e}")
        return {
            "type": "FeatureCollection",
            "features": [],
            "metadata": {
                "center": {"lat": lat, "lon": lon},
                "radius_meters": radius_meters,
                "count": 0,
                "error": str(e),
            },
        }


# ──────────────────────────────────────────────
# 2. GeoJSON Simplification
# ──────────────────────────────────────────────

def simplify_geojson(
    geojson: Dict[str, Any],
    tolerance: float = 0.001,
) -> Dict[str, Any]:
    """
    Simplify GeoJSON geometry to reduce file size.
    Uses Ramer-Douglas-Peucker algorithm via shapely if available.

    Args:
        geojson: Input GeoJSON dict
        tolerance: Simplification tolerance (higher = simpler)

    Returns:
        Simplified GeoJSON dict
    """
    try:
        from shapely.geometry import shape, mapping
        from shapely.geometry.collection import GeometryCollection

        features = geojson.get("features", [])
        simplified_features = []

        for feature in features:
            try:
                geom = shape(feature.get("geometry", {}))
                simplified_geom = geom.simplify(tolerance, preserve_topology=True)

                new_feature = {
                    "type": "Feature",
                    "geometry": mapping(simplified_geom),
                    "properties": feature.get("properties", {}),
                }
                simplified_features.append(new_feature)
            except Exception as e:
                # If simplification fails, keep original
                simplified_features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": simplified_features,
        }

    except ImportError:
        # shapely not available — return original
        return geojson


# ──────────────────────────────────────────────
# 3. Convert to Deck.gl format
# ──────────────────────────────────────────────

def convert_to_deckgl(
    geojson: Dict[str, Any],
    layer_type: str = "GeoJsonLayer",
    properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convert GeoJSON data to Deck.gl layer format for use with pydeck.

    Args:
        geojson: Input GeoJSON data
        layer_type: Deck.gl layer type
        properties: Additional layer properties

    Returns:
        Deck.gl layer configuration dict
    """
    if properties is None:
        properties = {
            "pickable": True,
            "opacity": 0.8,
            "stroked": True,
            "filled": True,
            "lineWidthMinPixels": 1,
            "getFillColor": "[200, 50, 50, 150]",
            "getLineColor": "[50, 50, 50, 200]",
        }

    deckgl_layer = {
        "@@type": layer_type,
        "data": geojson,
        **properties,
    }

    return deckgl_layer


def create_map_layers(geojson_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create multiple Deck.gl layers from GeoJSON data.

    Returns layers for:
    - Land polygons
    - Marker points (POIs)
    - Heatmap (price density)
    """
    layers = []

    # Land polygon layer
    land_layer = convert_to_deckgl(
        geojson_data,
        layer_type="GeoJsonLayer",
        properties={
            "id": "lands-layer",
            "pickable": True,
            "opacity": 0.6,
            "stroked": True,
            "filled": True,
            "lineWidthMinPixels": 2,
            "getFillColor": [100, 150, 200, 120],
            "getLineColor": [50, 50, 100, 200],
            "autoHighlight": True,
            "highlightColor": [255, 200, 50, 200],
        },
    )
    layers.append(land_layer)

    # POI marker layer
    if geojson_data.get("features"):
        poi_layer = convert_to_deckgl(
            geojson_data,
            layer_type="ScatterplotLayer",
            properties={
                "id": "pois-layer",
                "pickable": True,
                "opacity": 1.0,
                "radiusScale": 10,
                "radiusMinPixels": 4,
                "radiusMaxPixels": 20,
                "getPosition": "@@.geometry.coordinates",
                "getFillColor": [255, 100, 50, 200],
                "getRadius": 100,
            },
        )
        layers.append(poi_layer)

    return layers


# ──────────────────────────────────────────────
# 4. Mapbox GL JS Configuration
# ──────────────────────────────────────────────

def get_mapbox_config() -> MapConfig:
    """
    Get Mapbox GL JS configuration from environment variables.
    Falls back to a free tile provider if Mapbox token is not set.
    """
    token = os.getenv("MAPBOX_ACCESS_TOKEN", "")

    if token:
        return MapConfig(
            style_url="mapbox://styles/mapbox/light-v11",
            access_token=token,
        )
    else:
        # Fallback to free OpenStreetMap tiles
        logger.info("Mapbox token not set — using free OSM tiles")
        return MapConfig(
            style_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            access_token="",
        )


def get_map_html(
    geojson_data: Optional[Dict[str, Any]] = None,
    map_config: Optional[MapConfig] = None,
) -> str:
    """
    Generate lightweight map HTML using Mapbox GL JS or fallback.
    Replaces heavy Folium maps with streamlined rendering.

    Returns:
        HTML string for the map component
    """
    if map_config is None:
        map_config = get_mapbox_config()

    if geojson_data is None:
        geojson_data = {"type": "FeatureCollection", "features": []}

    geojson_str = json.dumps(geojson_data, ensure_ascii=False)

    if map_config.access_token:
        # Mapbox GL JS with token
        html = f"""
        <!DOCTYPE html>
        <html dir="rtl">
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <script src="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js"></script>
            <link href="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css" rel="stylesheet" />
            <style>
                body {{ margin: 0; padding: 0; }}
                #map {{ width: 100%; height: 100vh; }}
                .mapboxgl-popup-content {{ font-family: 'Noto Sans Arabic', sans-serif; padding: 15px; }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                mapboxgl.accessToken = '{map_config.access_token}';
                const map = new mapboxgl.Map({{
                    container: 'map',
                    style: '{map_config.style_url}',
                    center: [{map_config.center_lon}, {map_config.center_lat}],
                    zoom: {map_config.zoom},
                    maxZoom: {map_config.max_zoom},
                    minZoom: {map_config.min_zoom},
                }});

                map.addControl(new mapboxgl.NavigationControl(), 'top-left');
                map.addControl(new mapboxgl.ScaleControl(), 'bottom-left');

                // Add GeoJSON data
                const data = {geojson_str};
                if (data.features && data.features.length > 0) {{
                    map.on('load', () => {{
                        map.addSource('lands', {{
                            type: 'geojson',
                            data: data,
                        }});
                        map.addLayer({{
                            id: 'lands-fill',
                            type: 'fill',
                            source: 'lands',
                            paint: {{
                                'fill-color': ['case',
                                    ['==', ['get', 'status'], 'Available'], '#4CAF50',
                                    ['==', ['get', 'status'], 'Sold'], '#F44336',
                                    '#2196F3'
                                ],
                                'fill-opacity': 0.6,
                            }},
                        }});
                        map.addLayer({{
                            id: 'lands-outline',
                            type: 'line',
                            source: 'lands',
                            paint={{
                                'line-color': '#333',
                                'line-width': 1,
                            }},
                        }});
                    }});
                }}
            </script>
        </body>
        </html>
        """
    else:
        # Fallback: Leaflet with OSM tiles (lightweight)
        html = f"""
        <!DOCTYPE html>
        <html dir="rtl">
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <style>
                body {{ margin: 0; padding: 0; }}
                #map {{ width: 100%; height: 100vh; }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                const map = L.map('map').setView([{map_config.center_lat}, {map_config.center_lon}], {map_config.zoom});
                L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    attribution: '© OpenStreetMap',
                    maxZoom: {map_config.max_zoom},
                }}).addTo(map);

                const data = {geojson_str};
                if (data.features) {{
                    L.geoJSON(data, {{
                        style: function(feature) {{
                            return {{
                                color: feature.properties?.status === 'Available' ? '#4CAF50' : '#F44336',
                                weight: 1,
                                opacity: 0.8,
                                fillOpacity: 0.4,
                            }};
                        }},
                    }}).addTo(map);
                }}
            </script>
        </body>
        </html>
        """

    return html


# ──────────────────────────────────────────────
# 5. Performance Logging
# ──────────────────────────────────────────────

def log_map_performance(
    data_size_bytes: int,
    feature_count: int,
    render_time_ms: float,
):
    """
    Log map performance metrics for monitoring.
    Helps identify when data is too large and needs simplification.
    """
    logger.info(
        f"🗺️ Map performance: {data_size_bytes / 1024:.1f}KB, "
        f"{feature_count} features, {render_time_ms:.0f}ms render time"
    )

    if data_size_bytes > 5 * 1024 * 1024:  # 5MB
        logger.warning(f"⚠️ Map data too large ({data_size_bytes / 1024 / 1024:.1f}MB) — simplify!")
    elif data_size_bytes > 1 * 1024 * 1024:  # 1MB
        logger.info("Map data moderate size — consider simplification if slow")

    if feature_count > 10000:
        logger.warning(f"⚠️ Too many features ({feature_count}) — consider clustering")

    if render_time_ms > 2000:
        logger.warning(f"⚠️ Map rendering slow ({render_time_ms:.0f}ms) — optimize data")