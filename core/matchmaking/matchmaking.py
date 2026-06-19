"""
============================================================
Smart Land Management Copilot — Matchmaking Domain Models
============================================================
Models representing matchmaking results, scores, and analysis.
============================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(str, Enum):
    """Investment risk classification."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class RecommendationType(str, Enum):
    """Recommendation strength."""
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    CONSIDER = "Consider"
    AVOID = "Avoid"


@dataclass
class ScoreBreakdown:
    """Detailed scoring breakdown for a single criterion."""

    category: str
    max_score: float
    actual_score: float
    passed: bool
    detail: str = ""

    @property
    def percentage(self) -> float:
        """Percentage of max score achieved."""
        if self.max_score == 0:
            return 0.0
        return (self.actual_score / self.max_score) * 100


@dataclass
class MatchResult:
    """Complete matchmaking result for a single land."""

    land_id: str
    compatibility_percent: float
    score_breakdown: List[ScoreBreakdown] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    investment_risk: RiskLevel = RiskLevel.MEDIUM
    recommendation: RecommendationType = RecommendationType.CONSIDER
    land_data: Optional[Dict[str, Any]] = None

    @property
    def is_auction(self) -> bool:
        """Check if the matched land is an auction."""
        if self.land_data:
            return self.land_data.get("Investment_Status") == "Public Auction"
        return False

    def to_display_dict(self) -> Dict[str, Any]:
        """Serialize for UI rendering."""
        return {
            "Land_ID": self.land_id,
            "Compatibility_Percent": self.compatibility_percent,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "investment_risk": self.investment_risk.value,
            "recommendation": self.recommendation.value,
            "is_auction": self.is_auction,
            "score_breakdown": [
                {
                    "category": sb.category,
                    "max_score": sb.max_score,
                    "actual_score": sb.actual_score,
                    "percentage": sb.percentage,
                    "passed": sb.passed,
                    "detail": sb.detail,
                }
                for sb in self.score_breakdown
            ],
            **(self.land_data or {}),
        }


@dataclass
class MatchmakingReport:
    """Complete matchmaking analysis report."""

    criteria_summary: str
    results: List[MatchResult] = field(default_factory=list)
    total_lands_analyzed: int = 0
    top_recommendation: Optional[str] = None

    def get_top_results(self, n: int = 5) -> List[MatchResult]:
        """Get top N results by compatibility."""
        return sorted(self.results, key=lambda r: r.compatibility_percent, reverse=True)[:n]

    def get_auction_opportunities(self) -> List[MatchResult]:
        """Filter results that are auction lands."""
        return [r for r in self.results if r.is_auction]