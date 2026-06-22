"""
infrastructure.gis.map_optimizer
=================================
وحدة تحسين الخرائط مع fallback إلى Leaflet/OSM عند عدم توفر Mapbox token.

توفر:
    - get_mapbox_config(): قراءة إعدادات Mapbox من البيئة
    - get_map_html(): توليد HTML لخريطة مع fallback تلقائي
    - MapConfig: dataclass للإعدادات
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
# MapConfig
# ──────────────────────────────────────────────

@dataclass
class MapConfig:
    """إعدادات الخريطة."""
    access_token: str = ""                              # Mapbox token (فارغ = استخدم Leaflet fallback)
    style: str = "mapbox/streets-v12"
    center_lat: float = 30.0444                          # مركز افتراضي: القاهرة
    center_lng: float = 31.2357
    zoom: int = 6
    fallback_to_leaflet: bool = True
    width: str = "100%"
    height: str = "600px"
    markers: List[Dict[str, Any]] = field(default_factory=list)


# ──────────────────────────────────────────────
# قراءة الإعدادات
# ──────────────────────────────────────────────

def get_mapbox_config() -> MapConfig:
    """قراءة إعدادات Mapbox من متغيرات البيئة.

    لو MAPBOX_ACCESS_TOKEN غير مضبوط، يُرجع MapConfig مع token فارغ
    و fallback_to_leaflet=True لتفعيل الخريطة البديلة.
    """
    token = os.getenv("MAPBOX_ACCESS_TOKEN", "")
    return MapConfig(
        access_token=token,
        style=os.getenv("MAPBOX_STYLE", "mapbox/streets-v12"),
        center_lat=float(os.getenv("MAP_CENTER_LAT", "30.0444")),
        center_lng=float(os.getenv("MAP_CENTER_LNG", "31.2357")),
        zoom=int(os.getenv("MAP_ZOOM", "6")),
        fallback_to_leaflet=True,
    )


# ──────────────────────────────────────────────
# توليد HTML
# ──────────────────────────────────────────────

_LEAFLET_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>Smart Land Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    body, html {{ margin: 0; padding: 0; }}
    #map {{ width: {width}; height: {height}; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    var map = L.map('map').setView([{lat}, {lng}], {zoom});
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19
    }}).addTo(map);
    {markers_js}
  </script>
</body>
</html>"""

_MAPBOX_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>Smart Land Map</title>
  <link href="https://api.mapbox.com/mapbox-gl-js/v3.0.0/mapbox-gl.css" rel="stylesheet" />
  <script src="https://api.mapbox.com/mapbox-gl-js/v3.0.0/mapbox-gl.js"></script>
  <style>
    body, html {{ margin: 0; padding: 0; }}
    #map {{ width: {width}; height: {height}; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    mapboxgl.accessToken = '{token}';
    var map = new mapboxgl.Map({{
      container: 'map',
      style: 'mapbox://styles/{style}',
      center: [{lng}, {lat}],
      zoom: {zoom}
    }});
    {markers_js}
  </script>
</body>
</html>"""


def _build_markers_js(markers: List[Dict[str, Any]], use_mapbox: bool) -> str:
    """بناء كود JS للماركرز."""
    if not markers:
        return ""
    lines = []
    for m in markers:
        lat = m.get("lat", 30.0444)
        lng = m.get("lng", 31.2357)
        title = m.get("title", "").replace("'", "\\'")
        if use_mapbox:
            lines.append(
                f"new mapboxgl.Marker().setLngLat([{lng}, {lat}])"
                f".setPopup(new mapboxgl.Popup().setHTML('{title}')).addTo(map);"
            )
        else:
            lines.append(
                f"L.marker([{lat}, {lng}]).addTo(map).bindPopup('{title}');"
            )
    return "\n    ".join(lines)


def get_map_html(
    map_config: Optional[MapConfig] = None,
    markers: Optional[List[Dict[str, Any]]] = None,
    width: Optional[str] = None,
    height: Optional[str] = None,
) -> str:
    """توليد HTML للخريطة.

    لو Mapbox token متوفر، يستخدم Mapbox GL JS.
    وإلا، يقع back إلى Leaflet + OpenStreetMap (مجاني، لا يتطلب token).
    """
    config = map_config or get_mapbox_config()
    if width:
        config.width = width
    if height:
        config.height = height
    if markers is not None:
        config.markers = markers

    use_mapbox = bool(config.access_token)
    markers_js = _build_markers_js(config.markers, use_mapbox)

    if use_mapbox:
        return _MAPBOX_HTML_TEMPLATE.format(
            token=config.access_token,
            style=config.style,
            lat=config.center_lat,
            lng=config.center_lng,
            zoom=config.zoom,
            width=config.width,
            height=config.height,
            markers_js=markers_js,
        )
    return _LEAFLET_HTML_TEMPLATE.format(
        lat=config.center_lat,
        lng=config.center_lng,
        zoom=config.zoom,
        width=config.width,
        height=config.height,
        markers_js=markers_js,
    )


__all__ = ["MapConfig", "get_mapbox_config", "get_map_html"]
