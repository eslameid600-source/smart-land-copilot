"""models.land — facade with land-related dataclasses and constants."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# Usage color palette for the map (Egypt land-use visualization)
USAGE_COLORS: Dict[str, str] = {
    "residential": "#FFC107",
    "agricultural": "#4CAF50",
    "commercial": "#2196F3",
    "industrial": "#9C27B0",
    "tourism": "#00BCD4",
    "vacant": "#9E9E9E",
}


@dataclass
class LandRecord:
    """A canonical land record used by the map / search / RAG layers."""

    land_id: str
    land_name: str = ""
    governorate: str = ""
    region_city: str = ""
    total_area_sqm: int = 0
    price_per_sqm_egp: float = 0.0
    total_price_egp: float = 0.0
    usage_type: str = "vacant"
    status: str = "Available"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description_ar: Optional[str] = None
    images: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "land_id": self.land_id,
            "land_name": self.land_name,
            "governorate": self.governorate,
            "region_city": self.region_city,
            "total_area_sqm": self.total_area_sqm,
            "price_per_sqm_egp": self.price_per_sqm_egp,
            "total_price_egp": self.total_price_egp,
            "usage_type": self.usage_type,
            "status": self.status,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "description_ar": self.description_ar,
            "images": self.images,
            "metadata": self.metadata,
        }


@dataclass
class CreatorStudioSuitability:
    """Suitability assessment for creator-studio use case."""

    land_id: str
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)


@dataclass
class EnvironmentalData:
    """Environmental metadata for a land parcel."""

    land_id: str
    vegetation_index: Optional[float] = None
    aridity_index: Optional[float] = None
    water_table_depth_m: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class GreeneryDensityData:
    """Greenery density summary."""

    land_id: str
    density_pct: float = 0.0
    radius_m: int = 0
    samples: int = 0


@dataclass
class RadiusProfile:
    """Radius-based density profile around a point."""

    radius_m: int
    greenery_pct: float = 0.0
    service_count: int = 0
    saturation: str = "low"


@dataclass
class SaturationLevel:
    """Saturation level enum-like data class."""

    level: str = "low"
    pct: float = 0.0


@dataclass
class ServiceDensityData:
    """Service-density metrics for a land parcel."""

    land_id: str
    total_services: int = 0
    radius_profiles: List[RadiusProfile] = field(default_factory=list)
    saturation: SaturationLevel = field(default_factory=SaturationLevel)


# Broker allocation record (used by broker_delegation_service.py with broker_name / assigned_date)
@dataclass
class BrokerAllocation:
    """A broker allocation record for a land/auction.

    Compatible with the legacy broker_delegation_service which uses
    broker_name + assigned_date fields.
    """

    auction_id: str = ""
    broker_id: str = ""
    land_id: str = ""
    commission_pct: float = 2.5
    assigned_at: Optional[datetime] = None

    # Legacy fields used by api/routes/broker_delegation_service.py
    broker_name: str = ""
    assigned_date: str = ""


__all__ = [
    "USAGE_COLORS",
    "LandRecord",
    "CreatorStudioSuitability",
    "EnvironmentalData",
    "GreeneryDensityData",
    "RadiusProfile",
    "SaturationLevel",
    "ServiceDensityData",
    "BrokerAllocation",
]
