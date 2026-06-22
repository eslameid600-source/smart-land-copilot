"""services.map_service — facade re-exporting from config.map_service_2."""

from config.map_service_2 import (  # noqa: F401
    MapService,
    get_map_service,
    reset_map_service,
)


def build_land_map(lands=None, **kwargs):
    """Convenience helper — build a Folium map via the shared MapService."""
    svc = get_map_service()
    return svc.build_map(lands=lands, **kwargs) if hasattr(svc, "build_map") else None


def get_land_map_html(lands=None, **kwargs):
    """Convenience helper — return the land map as HTML."""
    fmap = build_land_map(lands=lands, **kwargs)
    if fmap is None:
        return "<div>Map unavailable</div>"
    try:
        return fmap._repr_html_()
    except Exception:
        return "<div>Map rendering failed</div>"


__all__ = [
    "MapService",
    "get_map_service",
    "reset_map_service",
    "build_land_map",
    "get_land_map_html",
]
