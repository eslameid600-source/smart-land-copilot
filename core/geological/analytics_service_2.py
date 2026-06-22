"""
============================================================
Smart Land Management Copilot — Analytics Service
============================================================
Provides aggregate analytics and statistics for the dashboard.

Design Pattern: Facade (simplifies access to complex stats)
SOLID:
  - SRP: Analytics and statistics only
  - DIP: Depends on repository, not raw data
============================================================
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from config.settings import AppConfig, get_settings
from data.repository import LandRepository, get_repository
from models.land import LandSummary

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Analytics and statistics service.

    Provides pre-computed and on-demand analytics for the
    Streamlit dashboard and reporting.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        repository: Optional[LandRepository] = None,
    ) -> None:
        self._config = config or get_settings()
        self._repo = repository or get_repository()

    def get_summary(self) -> LandSummary:
        """Get aggregate land database summary."""
        return self._repo.get_summary()

    def get_summary_dict(self) -> Dict[str, Any]:
        """Get summary as plain dict (for UI compatibility)."""
        s = self._repo.get_summary()
        return {
            "total_lands": s.total_lands,
            "total_area_sqm": s.total_area_sqm,
            "avg_price_per_sqm": s.avg_price_per_sqm,
            "auction_lands": s.auction_lands,
            "direct_sale_lands": s.direct_sale_lands,
            "usage_breakdown": s.usage_breakdown,
            "governorate_breakdown": s.governorate_breakdown,
        }

    def get_governorate_dataframe(self) -> pd.DataFrame:
        """Get governorate breakdown as DataFrame for sidebar display."""
        return self._repo.get_governorate_dataframe()

    def get_full_dataframe(self) -> pd.DataFrame:
        """Get all lands as DataFrame for data table display."""
        return self._repo.get_dataframe()

    def get_usage_categories(self) -> List[str]:
        """Get distinct usage categories."""
        return self._repo.get_usage_categories()

    def get_governorates(self) -> List[str]:
        """Get distinct governorates."""
        return self._repo.get_governorates()

    def get_auction_summary(self) -> List[Dict[str, Any]]:
        """Get summary of auction lands with key details."""
        auction_lands = self._repo.get_auctions()
        return [
            {
                "Land_ID": land.land_id,
                "Governorate": land.governorate,
                "Region_City": land.region_city,
                "Allowed_Usage": land.allowed_usage,
                "Total_Area_Sqm": land.total_area_sqm,
                "Price_Per_Sqm_EGP": land.price_per_sqm_egp,
                "Auction_Date": land.auction_date,
                "Starting_Price_Per_Sqm_EGP": land.starting_price_per_sqm_egp,
            }
            for land in auction_lands
        ]

    def get_price_range(self, usage: Optional[str] = None) -> Dict[str, int]:
        """Get min/max/avg price per sqm, optionally filtered by usage."""
        if usage:
            lands = self._repo.filter_by_usage(usage)
        else:
            lands = self._repo.get_all()

        if not lands:
            return {"min": 0, "max": 0, "avg": 0}

        prices = [land.price_per_sqm_egp for land in lands]
        return {
            "min": min(prices),
            "max": max(prices),
            "avg": round(sum(prices) / len(prices)),
        }

    def get_area_range(self, usage: Optional[str] = None) -> Dict[str, int]:
        """Get min/max/avg area, optionally filtered by usage."""
        if usage:
            lands = self._repo.filter_by_usage(usage)
        else:
            lands = self._repo.get_all()

        if not lands:
            return {"min": 0, "max": 0, "avg": 0}

        areas = [land.total_area_sqm for land in lands]
        return {
            "min": min(areas),
            "max": max(areas),
            "avg": round(sum(areas) / len(areas)),
        }


# ----------------------------------------------------------
# Module-level singleton
# ----------------------------------------------------------

_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service() -> AnalyticsService:
    """Get or create the global analytics service singleton."""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service


def reset_analytics_service() -> None:
    """Reset the analytics service singleton (useful for testing)."""
    global _analytics_service
    _analytics_service = None