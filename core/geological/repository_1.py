"""
============================================================
Smart Land Management Copilot — Land Repository
============================================================
Repository pattern implementation for land data access.

Provides a clean abstraction layer between data storage and
business logic. Supports both in-memory (dict-based) and
future database backends (SQLite, PostgreSQL).

Design Pattern: Repository Pattern (GoF)
SOLID Compliance:
  - SRP: Only data access concerns
  - DIP: Depends on LandRecord model, not concrete storage
  - OCP: Open for extension (add DB backends) without modification
============================================================
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from models.models.land import InvestmentStatus, LandRecord, LandSummary

logger = logging.getLogger(__name__)

class LandRepository:
    """
    Repository for land data access.

    Encapsulates all data retrieval logic and provides typed
    access to land records. The repository converts raw dicts
    to LandRecord domain objects.
    """

    def __init__(self) -> None:
        """Initialize repository and load data."""
        self._records: List[LandRecord] = []
        self._records_dict: Dict[str, LandRecord] = {}
        self._load_data()

    def _load_data(self) -> None:
        """Load and index all land records from the database module."""
        from data.land_database import LANDS_RAW
        self._records = [LandRecord.from_dict(d) for d in LANDS_RAW]
        self._records_dict = {r.land_id: r for r in self._records}
        logger.info('Loaded %d land records into repository', len(self._records))

    def get_all(self) -> List[LandRecord]:
        """Return all land records as domain objects."""
        return list(self._records)

    def get_all_dicts(self) -> List[Dict[str, Any]]:
        """Return all records as plain dicts (for backward compatibility)."""
        return [r.to_dict() for r in self._records]

    def get_by_id(self, land_id: str) -> Optional[LandRecord]:
        """Find a single land record by its unique ID. O(1) via dict lookup."""
        return self._records_dict.get(land_id)

    def get_by_id_dict(self, land_id: str) -> Optional[Dict[str, Any]]:
        """Find a single land record as dict by ID."""
        record = self.get_by_id(land_id)
        return record.to_dict() if record else None

    def count(self) -> int:
        """Return total number of land records."""
        return len(self._records)

    def search(self, usage: Optional[str]=None, governorate: Optional[str]=None, min_area: Optional[int]=None, max_price: Optional[int]=None, investment_status: Optional[str]=None, limit: Optional[int]=None) -> List[LandRecord]:
        """
        Multi-criteria search over land records.

        All parameters are optional; when provided, they act as
        AND filters (all must match).
        """
        results: List[LandRecord] = []
        for record in self._records:
            if usage and record.allowed_usage != usage:
                continue
            if governorate and record.governorate != governorate:
                continue
            if min_area is not None and record.total_area_sqm < min_area:
                continue
            if max_price is not None and record.price_per_sqm_egp > max_price:
                continue
            if investment_status and record.investment_status != investment_status:
                continue
            results.append(record)
        if limit:
            results = results[:limit]
        logger.debug('search() returned %d results (filters: %s)', len(results), {'usage': usage, 'governorate': governorate, 'min_area': min_area, 'max_price': max_price})
        return results

    def get_auctions(self) -> List[LandRecord]:
        """Return only lands available via Public Auction."""
        return self.search(investment_status=InvestmentStatus.PUBLIC_AUCTION.value)

    def get_direct_sales(self) -> List[LandRecord]:
        """Return only lands available via Direct Sale."""
        return self.search(investment_status=InvestmentStatus.DIRECT_SALE.value)

    def filter_by_usage(self, usage: Optional[str]=None) -> List[LandRecord]:
        """Return lands matching a specific usage type. 'All' or None = all."""
        if not usage or usage == 'All':
            return self.get_all()
        return self.search(usage=usage)

    def filter_by_usage_dicts(self, usage: Optional[str]=None) -> List[Dict[str, Any]]:
        """Same as filter_by_usage but returns dicts."""
        return [r.to_dict() for r in self.filter_by_usage(usage)]

    def get_usage_categories(self) -> List[str]:
        """Return distinct usage categories, sorted alphabetically."""
        return sorted({r.allowed_usage for r in self._records})

    def get_governorates(self) -> List[str]:
        """Return distinct governorates, sorted alphabetically."""
        return sorted({r.governorate for r in self._records})

    def get_summary(self) -> LandSummary:
        """Compute aggregate statistics for the dashboard."""
        total_area = sum((r.total_area_sqm for r in self._records))
        avg_price = sum((r.price_per_sqm_egp for r in self._records)) / max(len(self._records), 1)
        auction_count = sum((1 for r in self._records if r.is_auction))
        usage_counts: Dict[str, int] = {}
        gov_counts: Dict[str, int] = {}
        for r in self._records:
            usage_counts[r.allowed_usage] = usage_counts.get(r.allowed_usage, 0) + 1
            gov_counts[r.governorate] = gov_counts.get(r.governorate, 0) + 1
        return LandSummary(total_lands=len(self._records), total_area_sqm=total_area, avg_price_per_sqm=round(avg_price, 2), auction_lands=auction_count, direct_sale_lands=len(self._records) - auction_count, usage_breakdown=usage_counts, governorate_breakdown=gov_counts)

    def get_dataframe(self) -> pd.DataFrame:
        """Return all lands as a Pandas DataFrame."""
        return pd.DataFrame([r.to_dict() for r in self._records])

    def get_governorate_dataframe(self) -> pd.DataFrame:
        """Return governorate breakdown as DataFrame for sidebar display."""
        summary = self.get_summary()
        rows = [{'Governorate': gov, 'Count': count} for gov, count in sorted(summary.governorate_breakdown.items(), key=lambda x: x[1], reverse=True)]
        return pd.DataFrame(rows)

    def find_nearest(self, lat: float, lon: float, max_distance_deg: float=1.0) -> Optional[LandRecord]:
        """
        Find the nearest land to a given coordinate.
        Uses simple Euclidean distance in degree space (sufficient for this scale).
        """
        best_record: Optional[LandRecord] = None
        best_dist = float('inf')
        for record in self._records:
            dist = ((record.latitude - lat) ** 2 + (record.longitude - lon) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_record = record
        if best_record and best_dist <= max_distance_deg:
            return best_record
        return None

    def find_nearest_dict(self, lat: float, lon: float, max_distance_deg: float=1.0) -> Optional[Dict[str, Any]]:
        """Same as find_nearest but returns dict."""
        record = self.find_nearest(lat, lon, max_distance_deg)
        return record.to_dict() if record else None
_repo_instance: Optional[LandRepository] = None

def get_repository() -> LandRepository:
    """Get or create the global repository singleton."""
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = LandRepository()
    return _repo_instance

def reset_repository() -> None:
    """Reset the repository singleton (useful for testing)."""
    global _repo_instance
    _repo_instance = None