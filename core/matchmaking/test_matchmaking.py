"""
============================================================
Smart Land Management Copilot — Tests: Matchmaking
============================================================
Unit tests for the matchmaking scoring engine.
"""
import pytest
from models.models.models.investor import InvestorCriteria
from models.models.models.matchmaking import RecommendationType, RiskLevel

from config.settings import AppConfig, MatchmakingWeights
from services.matchmaking_service import MatchmakingService


@pytest.fixture
def config():
    return AppConfig(mock_mode=True, matchmaking_weights=MatchmakingWeights())

@pytest.fixture
def sample_land_dict():
    return {'Land_ID': 'TEST-01', 'Governorate': 'Cairo', 'Region_City': 'New Cairo', 'Latitude': 30.0, 'Longitude': 31.4, 'Total_Area_Sqm': 150000, 'Price_Per_Sqm_EGP': 5000, 'Soil_Mineral_Type': 'Sandy', 'Allowed_Usage': 'Industrial', 'Nearest_Highways': 'Ring Road', 'Utilities_Availability': 'Water, Electricity, Gas, Fiber-Optic', 'Investment_Status': 'Direct Sale', 'Auction_Date': None, 'Starting_Price_Per_Sqm_EGP': None, 'Gov_Feasibility_Notes': 'Test notes.', 'Radius_Meters': 269.0}

@pytest.fixture
def auction_land_dict(sample_land_dict):
    d = dict(sample_land_dict)
    d['Land_ID'] = 'TEST-AUC'
    d['Investment_Status'] = 'Public Auction'
    d['Auction_Date'] = '2026-08-15'
    d['Starting_Price_Per_Sqm_EGP'] = 4500
    return d

class TestInvestorCriteria:
    """Tests for InvestorCriteria model."""

    def test_empty_criteria(self):
        criteria = InvestorCriteria()
        assert criteria.target_usage is None
        assert criteria.min_area_sqm is None
        assert criteria.required_utilities == []

    def test_validation_passes(self):
        criteria = InvestorCriteria(min_area_sqm=100000, max_price_per_sqm=5000)
        issues = criteria.validate()
        assert len(issues) == 0

    def test_validation_fails_negative(self):
        criteria = InvestorCriteria(min_area_sqm=-100)
        issues = criteria.validate()
        assert len(issues) > 0

    def test_to_display_string(self):
        criteria = InvestorCriteria(target_usage='Industrial', min_area_sqm=100000, max_price_per_sqm=5000, required_utilities=['Gas', 'Fiber-Optic'])
        display = criteria.to_display_string()
        assert 'Industrial' in display
        assert '100,000' in display
        assert '5,000' in display
        assert 'Gas' in display

    def test_to_dict_roundtrip(self):
        criteria = InvestorCriteria(target_usage='Logistics', min_area_sqm=200000, max_price_per_sqm=3000, required_utilities=['Water'])
        d = criteria.to_dict()
        restored = InvestorCriteria.from_dict(d)
        assert restored.target_usage == 'Logistics'
        assert restored.min_area_sqm == 200000
        assert 'Water' in restored.required_utilities

class TestMatchmakingScoring:
    """Tests for the matchmaking scoring engine."""

    @staticmethod
    def _make_service(lands_data):
        from unittest.mock import MagicMock

        from models.models.models.land import LandRecord

        from config.settings import AppConfig, MatchmakingWeights
        mock_repo = MagicMock()
        mock_repo.get_all.return_value = [LandRecord.from_dict(d) for d in lands_data]
        config = AppConfig(mock_mode=True, matchmaking_weights=MatchmakingWeights())
        return MatchmakingService(config=config, repository=mock_repo)

    def test_perfect_match_high_score(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        criteria = InvestorCriteria(target_usage='Industrial', min_area_sqm=100000, max_price_per_sqm=10000, required_utilities=['Water', 'Electricity', 'Gas', 'Fiber-Optic'])
        report = svc.match(criteria)
        top = report.results[0]
        assert top.compatibility_percent >= 80

    def test_wrong_usage_lower_score(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        criteria = InvestorCriteria(target_usage='Agricultural', min_area_sqm=100000, max_price_per_sqm=10000)
        report = svc.match(criteria)
        for result in report.results:
            assert result.compatibility_percent < 80

    def test_area_too_small_partial_credit(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        criteria = InvestorCriteria(min_area_sqm=300000)
        report = svc.match(criteria)
        for result in report.results:
            area_bd = next((sb for sb in result.score_breakdown if sb.category == 'Area Match'), None)
            if area_bd:
                assert area_bd.actual_score < area_bd.max_score
                assert area_bd.passed is False

    def test_price_over_budget_partial_credit(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        criteria = InvestorCriteria(max_price_per_sqm=2000)
        report = svc.match(criteria)
        for result in report.results:
            price_bd = next((sb for sb in result.score_breakdown if sb.category == 'Price Match'), None)
            if price_bd:
                assert price_bd.passed is False

    def test_missing_utility_penalty(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        criteria = InvestorCriteria(required_utilities=['Solar', 'Sewage'])
        report = svc.match(criteria)
        for result in report.results:
            util_bd = next((sb for sb in result.score_breakdown if sb.category == 'Utilities Match'), None)
            if util_bd:
                assert util_bd.passed is False

    def test_auction_bonus(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        criteria = InvestorCriteria()
        report = svc.match(criteria)
        auction_result = next((r for r in report.results if r.land_id == 'TEST-AUC'), None)
        direct_result = next((r for r in report.results if r.land_id == 'TEST-01'), None)
        assert auction_result is not None
        assert direct_result is not None
        auction_bd = next((sb for sb in auction_result.score_breakdown if sb.category == 'Auction Opportunity'), None)
        direct_bd = next((sb for sb in direct_result.score_breakdown if sb.category == 'Auction Opportunity'), None)
        assert auction_bd.actual_score > direct_bd.actual_score

    def test_no_criteria_full_credit(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        criteria = InvestorCriteria()
        report = svc.match(criteria)
        for result in report.results:
            assert result.compatibility_percent >= 90

    def test_report_total_lands(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        report = svc.match(InvestorCriteria())
        assert report.total_lands_analyzed == 2

    def test_risk_classification(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        report = svc.match(InvestorCriteria(target_usage='Industrial'))
        for result in report.results:
            assert isinstance(result.investment_risk, RiskLevel)
            assert isinstance(result.recommendation, RecommendationType)

    def test_strengths_and_weaknesses_populated(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        criteria = InvestorCriteria(target_usage='Agricultural', min_area_sqm=300000, required_utilities=['Sewage'])
        report = svc.match(criteria)
        for result in report.results:
            assert len(result.strengths) + len(result.weaknesses) > 0

    def test_format_for_llm(self, sample_land_dict, auction_land_dict):
        svc = self._make_service([sample_land_dict, auction_land_dict])
        report = svc.match(InvestorCriteria())
        llm_text = svc.format_for_llm(report)
        assert 'RANKED LAND RESULTS' in llm_text
        assert 'Compatibility:' in llm_text
        assert 'Risk Level' in llm_text