"""
============================================================
Smart Land Management Copilot — Tests: RAG Service
============================================================
Unit tests for the RAG search engine.
"""
import pytest
from unittest.mock import patch, MagicMock
from services.rag_service import RAGService, QueryIntent
from models.models.land import LandRecord

@pytest.fixture
def sample_lands():
    """Create sample land records for testing."""
    return [{'Land_ID': 'TEST-01', 'Governorate': 'Cairo', 'Region_City': 'New Cairo', 'Latitude': 30.0, 'Longitude': 31.4, 'Total_Area_Sqm': 100000, 'Price_Per_Sqm_EGP': 5000, 'Soil_Mineral_Type': 'Sandy', 'Allowed_Usage': 'Industrial', 'Nearest_Highways': 'Ring Road, Sokhna Road', 'Utilities_Availability': 'Water, Electricity, Gas, Fiber-Optic', 'Investment_Status': 'Direct Sale', 'Auction_Date': None, 'Starting_Price_Per_Sqm_EGP': None, 'Gov_Feasibility_Notes': 'Test notes.', 'Radius_Meters': 220.0}, {'Land_ID': 'TEST-02', 'Governorate': 'Alexandria', 'Region_City': 'Borg El Arab', 'Latitude': 30.9, 'Longitude': 29.5, 'Total_Area_Sqm': 50000, 'Price_Per_Sqm_EGP': 4000, 'Soil_Mineral_Type': 'Limestone', 'Allowed_Usage': 'Logistics', 'Nearest_Highways': 'Cairo-Alexandria Desert Road', 'Utilities_Availability': 'Water, Electricity', 'Investment_Status': 'Public Auction', 'Auction_Date': '2026-09-20', 'Starting_Price_Per_Sqm_EGP': 3800, 'Gov_Feasibility_Notes': 'Near port.', 'Radius_Meters': 155.0}]

@pytest.fixture
def rag_service(sample_lands):
    """Create a RAGService with mocked repository."""
    from config.settings import AppConfig, ScoringWeights, MatchmakingWeights, GLMConfig, SecurityConfig, MapConfig
    config = AppConfig(mock_mode=True, scoring_weights=ScoringWeights())
    mock_repo = MagicMock()
    mock_repo.get_all_dicts.return_value = sample_lands
    return RAGService(config=config, repository=mock_repo)

class TestExtractIntent:
    """Tests for query intent extraction."""

    def test_extract_usage_industrial(self, rag_service):
        intent = rag_service.extract_intent('show me industrial land')
        assert intent.target_usage == 'Industrial'

    def test_extract_usage_warehouse(self, rag_service):
        intent = rag_service.extract_intent('I need a warehouse')
        assert intent.target_usage == 'Logistics'

    def test_extract_usage_farming(self, rag_service):
        intent = rag_service.extract_intent('farming land near Cairo')
        assert intent.target_usage == 'Agricultural'
        assert intent.target_gov == 'Cairo'

    def test_extract_governorate(self, rag_service):
        intent = rag_service.extract_intent('land in Alexandria')
        assert intent.target_gov == 'Alexandria'

    def test_extract_min_area(self, rag_service):
        intent = rag_service.extract_intent('at least 100000 sqm')
        assert intent.min_area == 100000

    def test_extract_max_price(self, rag_service):
        intent = rag_service.extract_intent('under 5000 EGP')
        assert intent.max_price == 5000

    def test_extract_utilities(self, rag_service):
        intent = rag_service.extract_intent('land with gas and electricity')
        assert 'gas' in intent.utility_keywords
        assert 'electricity' in intent.utility_keywords

    def test_extract_transport(self, rag_service):
        intent = rag_service.extract_intent('near highway and port')
        assert 'highway' in intent.transport_keywords
        assert 'port' in intent.transport_keywords

    def test_empty_query(self, rag_service):
        intent = rag_service.extract_intent('')
        assert intent.target_usage is None
        assert intent.target_gov is None

    def test_has_filters(self, rag_service):
        intent = rag_service.extract_intent('industrial land in Cairo')
        assert intent.has_filters is True

    def test_no_filters(self, rag_service):
        intent = rag_service.extract_intent('tell me about land')
        assert intent.has_filters is False

class TestSearch:
    """Tests for the search pipeline."""

    def test_search_returns_results(self, rag_service, sample_lands):
        results = rag_service.search('industrial land in Cairo')
        assert len(results) > 0
        assert isinstance(results[0], tuple)
        assert isinstance(results[0][0], dict)
        assert isinstance(results[0][1], int)

    def test_search_top_k(self, rag_service):
        results = rag_service.search('land', top_k=1)
        assert len(results) <= 1

    def test_search_min_score(self, rag_service):
        results = rag_service.search('industrial land', min_score=50)
        for _, score in results:
            assert score >= 50

    def test_search_no_results(self, rag_service):
        results = rag_service.search('nonexistent category xyz123', min_score=1)
        assert len(results) == 0

    def test_search_sorted_by_score(self, rag_service):
        results = rag_service.search('industrial')
        for i in range(1, len(results)):
            assert results[i][1] <= results[i - 1][1]

    def test_search_caching(self, rag_service):
        rag_service.search('industrial')
        rag_service.search('industrial')
        assert len(rag_service._cache) == 1

class TestBuildContext:
    """Tests for context formatting."""

    def test_empty_results(self, rag_service):
        context = rag_service.build_context([])
        assert 'No matching land records' in context

    def test_scored_results(self, rag_service, sample_lands):
        results = [(sample_lands[0], 85)]
        context = rag_service.build_context(results)
        assert 'TEST-01' in context
        assert '85/100' in context

    def test_compatibility_results(self, rag_service, sample_lands):
        land = sample_lands[0].copy()
        land['Compatibility_Percent'] = 72.5
        context = rag_service.build_context([land])
        assert '72.5%' in context

class TestRerank:
    """Tests for reranking."""

    def test_rerank_preserves_order(self, rag_service, sample_lands):
        results = [(sample_lands[0], 80), (sample_lands[1], 60)]
        reranked = rag_service.rerank(results, 'industrial land in Cairo')
        assert len(reranked) == 2

    def test_rerank_empty(self, rag_service):
        assert rag_service.rerank([], '') == []

    def test_clear_cache(self, rag_service):
        rag_service.search('test')
        rag_service.clear_cache()
        assert len(rag_service._cache) == 0