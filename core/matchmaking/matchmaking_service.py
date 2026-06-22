"""
============================================================
Smart Land Management Copilot — Matchmaking Service
============================================================
Advanced compatibility scoring engine for investor-land matching.

Features:
  - Weighted multi-criteria scoring (configurable weights)
  - Detailed score breakdowns per criterion
  - Strengths/weaknesses extraction
  - Investment risk classification
  - Recommendation generation (Strong Buy / Buy / Consider / Avoid)
  - Full report generation with LLM context formatting

Scoring Dimensions (total = 100%):
  1. Usage Match               (default 30%)
  2. Area Match                (default 20%)
  3. Price Match               (default 20%)
  4. Utilities Match           (default 20%)
  5. Auction Opportunity       (default 10%)

Design Pattern: Strategy (scoring weights), Builder (report)
SOLID:
  - SRP: Matchmaking logic only
  - OCP: New criteria via new score methods
  - LSP: MatchResult is fully substitutable
  - ISP: Separate methods per scoring dimension
  - DIP: Depends on models, not UI or storage
============================================================
"""
from __future__ import annotations

import logging
from typing import List, Optional

from data.repository import LandRepository, get_repository
from models.models.models.investor import InvestorCriteria
from models.models.models.land import LandRecord
from models.models.models.matchmaking import (
    MatchmakingReport,
    MatchResult,
    RecommendationType,
    RiskLevel,
    ScoreBreakdown,
)

from config.settings import AppConfig, get_settings

logger = logging.getLogger(__name__)

class MatchmakingService:
    """
    Advanced matchmaking engine.

    Compares investor criteria against all available lands
    and produces a ranked compatibility report.
    """

    def __init__(self, config: Optional[AppConfig]=None, repository: Optional[LandRepository]=None) -> None:
        self._config = config or get_settings()
        self._repo = repository or get_repository()
        self._weights = self._config.matchmaking_weights

    def match(self, criteria: InvestorCriteria) -> MatchmakingReport:
        """
        Run the full matchmaking pipeline.

        Args:
            criteria: Structured investor requirements

        Returns:
            MatchmakingReport with all lands ranked by compatibility.
        """
        warnings = criteria.validate()
        for w in warnings:
            logger.warning('Criteria validation: %s', w)
        lands = self._repo.get_all()
        results: List[MatchResult] = []
        for land in lands:
            result = self._score_land(land, criteria)
            results.append(result)
        results.sort(key=lambda r: r.compatibility_percent, reverse=True)
        top_rec = None
        if results:
            top = results[0]
            top_rec = f'{top.land_id} ({top.compatibility_percent}%) — {top.recommendation.value}'
        report = MatchmakingReport(criteria_summary=criteria.to_display_string(), results=results, total_lands_analyzed=len(lands), top_recommendation=top_rec)
        logger.info('Matchmaking complete: %d lands analyzed, top=%s (%.1f%%)', len(lands), results[0].land_id if results else 'N/A', results[0].compatibility_percent if results else 0)
        return report

    def format_for_llm(self, report: MatchmakingReport) -> str:
        """Format a matchmaking report into text for LLM injection."""
        if not report.results:
            return 'No matching land records found in the database.'
        lines = ['RANKED LAND RESULTS (Matchmaking Compatibility)', '=' * 60]
        for result in report.results:
            r = result.land_data or {}
            lines.append(f"\n[Land: {result.land_id}]  Compatibility: {result.compatibility_percent}%\n  Location       : {r.get('Governorate', 'N/A')} - {r.get('Region_City', 'N/A')}\n  Area           : {r.get('Total_Area_Sqm', 'N/A'):,} sqm\n  Price/sqm      : {r.get('Price_Per_Sqm_EGP', 'N/A'):,} EGP\n  Usage          : {r.get('Allowed_Usage', 'N/A')}\n  Risk Level     : {result.investment_risk.value}\n  Recommendation : {result.recommendation.value}\n  Strengths      : {'; '.join(result.strengths) or 'None identified'}\n  Weaknesses     : {'; '.join(result.weaknesses) or 'None identified'}\n")
            if result.is_auction:
                lines.append(f"  *** AUCTION *** Date: {r.get('Auction_Date', 'N/A')}, Starting: {r.get('Starting_Price_Per_Sqm_EGP', 'N/A'):,} EGP/m2\n")
            lines.append('  Score Breakdown:\n' + '\n'.join((f"    - {sb.category}: {sb.actual_score}/{sb.max_score} ({sb.percentage:.0f}%) {('OK' if sb.passed else 'MISS')} — {sb.detail}" for sb in result.score_breakdown)))
        return '\n'.join(lines)

    def _score_land(self, land: LandRecord, criteria: InvestorCriteria) -> MatchResult:
        """Score a single land against investor criteria."""
        w = self._weights
        breakdowns: List[ScoreBreakdown] = []
        strengths: List[str] = []
        weaknesses: List[str] = []
        total_score = 0.0
        usage_score, usage_bd = self._score_usage(land, criteria, w.usage_match)
        breakdowns.append(usage_bd)
        total_score += usage_score
        if usage_bd.passed:
            strengths.append(f'Correct usage type: {land.allowed_usage}')
        elif criteria.target_usage:
            weaknesses.append(f'Usage mismatch: {land.allowed_usage} (wanted {criteria.target_usage})')
        area_score, area_bd = self._score_area(land, criteria, w.area_match)
        breakdowns.append(area_bd)
        total_score += area_score
        if area_bd.passed:
            strengths.append(f'Area meets requirement: {land.total_area_sqm:,} sqm')
        elif criteria.min_area_sqm:
            weaknesses.append(f'Area insufficient: {land.total_area_sqm:,} < {criteria.min_area_sqm:,} sqm')
        price_score, price_bd = self._score_price(land, criteria, w.price_match)
        breakdowns.append(price_bd)
        total_score += price_score
        if price_bd.passed:
            strengths.append(f'Price within budget: {land.price_per_sqm_egp:,} EGP/sqm')
        elif criteria.max_price_per_sqm:
            weaknesses.append(f'Price over budget: {land.price_per_sqm_egp:,} > {criteria.max_price_per_sqm:,} EGP/sqm')
        util_score, util_bd = self._score_utilities(land, criteria, w.utilities_match)
        breakdowns.append(util_bd)
        total_score += util_score
        if util_bd.passed:
            strengths.append('All required utilities available')
        elif criteria.required_utilities:
            weaknesses.append(f'Missing: {util_bd.detail}')
        auction_score, auction_bd = self._score_auction(land, criteria, w.auction_opportunity)
        breakdowns.append(auction_bd)
        total_score += auction_score
        if land.is_auction:
            strengths.append(f'Auction opportunity on {land.auction_date}')
        compat = round(total_score, 1)
        risk = self._classify_risk(land, compat, weaknesses)
        recommendation = self._classify_recommendation(compat, risk, weaknesses)
        return MatchResult(land_id=land.land_id, compatibility_percent=compat, score_breakdown=breakdowns, strengths=strengths, weaknesses=weaknesses, investment_risk=risk, recommendation=recommendation, land_data=land.to_dict())

    @staticmethod
    def _score_usage(land: LandRecord, criteria: InvestorCriteria, max_score: float) -> tuple[float, ScoreBreakdown]:
        """Score usage type match."""
        if not criteria.target_usage:
            return (max_score, ScoreBreakdown(category='Usage Match', max_score=max_score, actual_score=max_score, passed=True, detail='No preference specified'))
        if land.allowed_usage == criteria.target_usage:
            return (max_score, ScoreBreakdown(category='Usage Match', max_score=max_score, actual_score=max_score, passed=True, detail=f'Exact match: {land.allowed_usage}'))
        return (0.0, ScoreBreakdown(category='Usage Match', max_score=max_score, actual_score=0.0, passed=False, detail=f'Want {criteria.target_usage}, got {land.allowed_usage}'))

    @staticmethod
    def _score_area(land: LandRecord, criteria: InvestorCriteria, max_score: float) -> tuple[float, ScoreBreakdown]:
        """Score area requirement match with partial credit."""
        if not criteria.min_area_sqm:
            return (max_score, ScoreBreakdown(category='Area Match', max_score=max_score, actual_score=max_score, passed=True, detail='No minimum specified'))
        if land.total_area_sqm >= criteria.min_area_sqm:
            return (max_score, ScoreBreakdown(category='Area Match', max_score=max_score, actual_score=max_score, passed=True, detail=f'{land.total_area_sqm:,} >= {criteria.min_area_sqm:,} sqm'))
        ratio = land.total_area_sqm / criteria.min_area_sqm
        partial = ratio * max_score
        return (partial, ScoreBreakdown(category='Area Match', max_score=max_score, actual_score=round(partial, 1), passed=False, detail=f'{land.total_area_sqm:,} < {criteria.min_area_sqm:,} sqm ({ratio:.0%} of required)'))

    @staticmethod
    def _score_price(land: LandRecord, criteria: InvestorCriteria, max_score: float) -> tuple[float, ScoreBreakdown]:
        """Score price budget match with partial credit."""
        if not criteria.max_price_per_sqm:
            return (max_score, ScoreBreakdown(category='Price Match', max_score=max_score, actual_score=max_score, passed=True, detail='No budget specified'))
        if land.price_per_sqm_egp <= criteria.max_price_per_sqm:
            return (max_score, ScoreBreakdown(category='Price Match', max_score=max_score, actual_score=max_score, passed=True, detail=f'{land.price_per_sqm_egp:,} <= {criteria.max_price_per_sqm:,} EGP/sqm'))
        ratio = criteria.max_price_per_sqm / land.price_per_sqm_egp
        partial = min(ratio, 1.0) * max_score
        return (partial, ScoreBreakdown(category='Price Match', max_score=max_score, actual_score=round(partial, 1), passed=False, detail=f'{land.price_per_sqm_egp:,} > {criteria.max_price_per_sqm:,} EGP/sqm ({ratio:.0%} of budget)'))

    @staticmethod
    def _score_utilities(land: LandRecord, criteria: InvestorCriteria, max_score: float) -> tuple[float, ScoreBreakdown]:
        """Score utilities availability match."""
        if not criteria.required_utilities:
            return (max_score, ScoreBreakdown(category='Utilities Match', max_score=max_score, actual_score=max_score, passed=True, detail='No utility preference'))
        land_utils_lower = land.utilities_availability.lower()
        matched = []
        missing = []
        for util in criteria.required_utilities:
            if util.lower() in land_utils_lower:
                matched.append(util)
            else:
                missing.append(util)
        if not missing:
            return (max_score, ScoreBreakdown(category='Utilities Match', max_score=max_score, actual_score=max_score, passed=True, detail='All required: ' + ', '.join(matched)))
        score = len(matched) / len(criteria.required_utilities) * max_score
        return (score, ScoreBreakdown(category='Utilities Match', max_score=max_score, actual_score=round(score, 1), passed=False, detail=f"Missing: {', '.join(missing)}"))

    @staticmethod
    def _score_auction(land: LandRecord, criteria: InvestorCriteria, max_score: float) -> tuple[float, ScoreBreakdown]:
        """Score auction opportunity bonus."""
        if land.is_auction:
            detail = f'Auction on {land.auction_date} (starting {land.starting_price_per_sqm_egp:,} EGP/m2)'
            return (max_score, ScoreBreakdown(category='Auction Opportunity', max_score=max_score, actual_score=max_score, passed=True, detail=detail))
        return (max_score * 0.5, ScoreBreakdown(category='Auction Opportunity', max_score=max_score, actual_score=round(max_score * 0.5, 1), passed=False, detail='Direct sale (no auction)'))

    @staticmethod
    def _classify_risk(land: LandRecord, compatibility: float, weaknesses: List[str]) -> RiskLevel:
        """Classify investment risk level."""
        critical_count = len(weaknesses)
        if compatibility >= 80 and critical_count == 0:
            return RiskLevel.LOW
        elif compatibility >= 60 or critical_count <= 1:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.HIGH

    @staticmethod
    def _classify_recommendation(compatibility: float, risk: RiskLevel, weaknesses: List[str]) -> RecommendationType:
        """Generate investment recommendation."""
        if compatibility >= 85 and risk == RiskLevel.LOW:
            return RecommendationType.STRONG_BUY
        elif compatibility >= 65:
            return RecommendationType.BUY
        elif compatibility >= 40:
            return RecommendationType.CONSIDER
        else:
            return RecommendationType.AVOID
_matchmaking_service: Optional[MatchmakingService] = None

def get_matchmaking_service() -> MatchmakingService:
    """Get or create the global matchmaking service singleton."""
    global _matchmaking_service
    if _matchmaking_service is None:
        _matchmaking_service = MatchmakingService()
    return _matchmaking_service

def reset_matchmaking_service() -> None:
    """Reset the matchmaking service singleton (useful for testing)."""
    global _matchmaking_service
    _matchmaking_service = None