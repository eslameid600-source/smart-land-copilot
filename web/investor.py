"""
============================================================
Smart Land Management Copilot — Investor Domain Models
============================================================
Models representing investor criteria for matchmaking.
============================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class InvestorCriteria:
    """Structured investor requirements for proactive matchmaking."""

    target_usage: Optional[str] = None
    min_area_sqm: Optional[int] = None
    max_price_per_sqm: Optional[int] = None
    required_utilities: List[str] = field(default_factory=list)
    preferred_governorate: Optional[str] = None
    investment_type_preference: Optional[str] = None  # "Direct Sale" or "Public Auction"

    def validate(self) -> List[str]:
        """Validate criteria and return list of warnings."""
        issues: List[str] = []
        if self.min_area_sqm is not None and self.min_area_sqm <= 0:
            issues.append("Minimum area must be positive")
        if self.max_price_per_sqm is not None and self.max_price_per_sqm <= 0:
            issues.append("Maximum price must be positive")
        return issues

    def to_display_string(self) -> str:
        """Human-readable summary for LLM prompts."""
        parts: List[str] = []
        if self.target_usage:
            parts.append(f"Usage: {self.target_usage}")
        if self.min_area_sqm:
            parts.append(f"Min Area: {self.min_area_sqm:,} sqm")
        if self.max_price_per_sqm:
            parts.append(f"Max Price: {self.max_price_per_sqm:,} EGP/sqm")
        if self.required_utilities:
            parts.append(f"Required Utilities: {', '.join(self.required_utilities)}")
        if self.preferred_governorate:
            parts.append(f"Preferred Governorate: {self.preferred_governorate}")
        if self.investment_type_preference:
            parts.append(f"Investment Type: {self.investment_type_preference}")
        return "; ".join(parts) if parts else "No specific criteria"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "target_usage": self.target_usage,
            "min_area_sqm": self.min_area_sqm,
            "max_price_per_sqm": self.max_price_per_sqm,
            "required_utilities": self.required_utilities,
            "preferred_governorate": self.preferred_governorate,
            "investment_type_preference": self.investment_type_preference,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvestorCriteria":
        """Deserialize from dictionary."""
        return cls(
            target_usage=data.get("target_usage"),
            min_area_sqm=data.get("min_area_sqm"),
            max_price_per_sqm=data.get("max_price_per_sqm"),
            required_utilities=data.get("required_utilities", []),
            preferred_governorate=data.get("preferred_governorate"),
            investment_type_preference=data.get("investment_type_preference"),
        )