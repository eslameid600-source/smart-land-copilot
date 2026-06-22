"""services.environmental_service — facade re-exporting from config.environmental_service_1."""

from config.environmental_service_1 import (  # noqa: F401
    EnvironmentalService,
    get_environmental_service,
)


def get_environmental_data(land_id: str):
    """Convenience helper — fetch environmental data for a single land."""
    svc = get_environmental_service()
    return svc.get_environmental_data(land_id) if hasattr(svc, "get_environmental_data") else None


__all__ = ["EnvironmentalService", "get_environmental_service", "get_environmental_data"]
