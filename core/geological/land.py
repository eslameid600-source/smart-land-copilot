"""
============================================================
Smart Land Management Copilot — Land Domain Models
============================================================
Pydantic-style dataclass models for land records.
Provides type safety, validation, and serialization.
============================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class UsageType(str, Enum):
    """Allowed land usage categories."""
    INDUSTRIAL = "Industrial"
    AGRICULTURAL = "Agricultural"
    LOGISTICS = "Logistics"
    RESIDENTIAL = "Residential"


class InvestmentStatus(str, Enum):
    """Investment availability status."""
    DIRECT_SALE = "Direct Sale"
    PUBLIC_AUCTION = "Public Auction"


# Color mapping for map markers
USAGE_COLORS: Dict[str, str] = {
    UsageType.INDUSTRIAL.value: "#e74c3c",
    UsageType.AGRICULTURAL.value: "#27ae60",
    UsageType.LOGISTICS.value: "#2980b9",
    UsageType.RESIDENTIAL.value: "#f39c12",
}

USAGE_ICONS: Dict[str, str] = {
    UsageType.INDUSTRIAL.value: "industry",
    UsageType.AGRICULTURAL.value: "leaf",
    UsageType.LOGISTICS.value: "warehouse",
    UsageType.RESIDENTIAL.value: "home",
}

ALL_UTILITIES: List[str] = [
    "Water",
    "Electricity",
    "Gas",
    "Fiber-Optic",
]


@dataclass
class LandRecord:
    """Single land parcel record with full type safety."""

    land_id: str
    governorate: str
    region_city: str
    latitude: float
    longitude: float
    total_area_sqm: int
    price_per_sqm_egp: int
    soil_mineral_type: str
    allowed_usage: str
    nearest_highways: str
    utilities_availability: str
    gov_feasibility_notes: str
    investment_status: str = InvestmentStatus.DIRECT_SALE.value
    auction_date: Optional[str] = None
    starting_price_per_sqm_egp: Optional[int] = None
    radius_meters: float = 0.0

    def __post_init__(self) -> None:
        """Validate data after initialization."""
        if self.total_area_sqm <= 0:
            raise ValueError(f"Land {self.land_id}: total_area_sqm must be > 0")
        if self.price_per_sqm_egp <= 0:
            raise ValueError(f"Land {self.land_id}: price_per_sqm_egp must be > 0")
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"Land {self.land_id}: invalid latitude {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"Land {self.land_id}: invalid longitude {self.longitude}")
        if self.allowed_usage not in [u.value for u in UsageType]:
            raise ValueError(f"Land {self.land_id}: unknown usage '{self.allowed_usage}'")
        if self.investment_status not in [s.value for s in InvestmentStatus]:
            raise ValueError(f"Land {self.land_id}: unknown status '{self.investment_status}'")
        if self.radius_meters <= 0:
            import math
            object.__setattr__(self, "radius_meters",
                               round(math.sqrt(self.total_area_sqm / math.pi) * 1.5, 1))

    @property
    def is_auction(self) -> bool:
        """Check if this land is available via public auction."""
        return self.investment_status == InvestmentStatus.PUBLIC_AUCTION.value

    @property
    def total_price_egp(self) -> int:
        """Calculate total land price in EGP."""
        return self.total_area_sqm * self.price_per_sqm_egp

    @property
    def utilities_list(self) -> List[str]:
        """Parse utilities string into a list."""
        return [u.strip() for u in self.utilities_availability.split(",") if u.strip()]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary (camelCase keys for backward compatibility)."""
        return {
            "Land_ID": self.land_id,
            "Governorate": self.governorate,
            "Region_City": self.region_city,
            "Latitude": self.latitude,
            "Longitude": self.longitude,
            "Total_Area_Sqm": self.total_area_sqm,
            "Price_Per_Sqm_EGP": self.price_per_sqm_egp,
            "Soil_Mineral_Type": self.soil_mineral_type,
            "Allowed_Usage": self.allowed_usage,
            "Nearest_Highways": self.nearest_highways,
            "Utilities_Availability": self.utilities_availability,
            "Gov_Feasibility_Notes": self.gov_feasibility_notes,
            "Investment_Status": self.investment_status,
            "Auction_Date": self.auction_date,
            "Starting_Price_Per_Sqm_EGP": self.starting_price_per_sqm_egp,
            "Radius_Meters": self.radius_meters,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LandRecord":
        """Deserialize from dictionary (supports both camelCase and snake_case)."""
        mapping = {
            "land_id": ("Land_ID", "land_id"),
            "governorate": ("Governorate", "governorate"),
            "region_city": ("Region_City", "region_city"),
            "latitude": ("Latitude", "latitude"),
            "longitude": ("Longitude", "longitude"),
            "total_area_sqm": ("Total_Area_Sqm", "total_area_sqm"),
            "price_per_sqm_egp": ("Price_Per_Sqm_EGP", "price_per_sqm_egp"),
            "soil_mineral_type": ("Soil_Mineral_Type", "soil_mineral_type"),
            "allowed_usage": ("Allowed_Usage", "allowed_usage"),
            "nearest_highways": ("Nearest_Highways", "nearest_highways"),
            "utilities_availability": ("Utilities_Availability", "utilities_availability"),
            "gov_feasibility_notes": ("Gov_Feasibility_Notes", "gov_feasibility_notes"),
            "investment_status": ("Investment_Status", "investment_status"),
            "auction_date": ("Auction_Date", "auction_date"),
            "starting_price_per_sqm_egp": ("Starting_Price_Per_Sqm_EGP", "starting_price_per_sqm_egp"),
            "radius_meters": ("Radius_Meters", "radius_meters"),
        }

        def _get(field_names: tuple) -> Any:
            for name in field_names:
                if name in data:
                    return data[name]
            return None

        return cls(
            land_id=_get(mapping["land_id"]),
            governorate=_get(mapping["governorate"]),
            region_city=_get(mapping["region_city"]),
            latitude=_get(mapping["latitude"]),
            longitude=_get(mapping["longitude"]),
            total_area_sqm=_get(mapping["total_area_sqm"]),
            price_per_sqm_egp=_get(mapping["price_per_sqm_egp"]),
            soil_mineral_type=_get(mapping["soil_mineral_type"]),
            allowed_usage=_get(mapping["allowed_usage"]),
            nearest_highways=_get(mapping["nearest_highways"]),
            utilities_availability=_get(mapping["utilities_availability"]),
            gov_feasibility_notes=_get(mapping["gov_feasibility_notes"]),
            investment_status=_get(mapping["investment_status"]) or InvestmentStatus.DIRECT_SALE.value,
            auction_date=_get(mapping["auction_date"]),
            starting_price_per_sqm_egp=_get(mapping["starting_price_per_sqm_egp"]),
            radius_meters=_get(mapping["radius_meters"]) or 0.0,
        )


@dataclass
class LandSummary:
    """Aggregate statistics for the dashboard."""

    total_lands: int
    total_area_sqm: int
    avg_price_per_sqm: float
    auction_lands: int
    direct_sale_lands: int
    usage_breakdown: Dict[str, int]
    governorate_breakdown: Dict[str, int]