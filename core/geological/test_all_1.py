"""
Smart Land Management Copilot — Tests
=======================================
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestLandDatabase:
    """Tests for the land database module."""

    def test_get_all_lands(self):
        from data.land_database import get_all_lands
        lands = get_all_lands()
        assert isinstance(lands, list)
        assert len(lands) == 10
        assert all("Land_ID" in land for land in lands)

    def test_get_land_by_id(self):
        from data.land_database import get_land_by_id
        land = get_land_by_id("EG-CAI-01")
        assert land is not None
        assert land["Governorate"] == "Cairo"
        assert get_land_by_id("NONEXISTENT") is None

    def test_get_land_dataframe(self):
        from data.land_database import get_land_dataframe
        df = get_land_dataframe()
        assert len(df) == 10
        assert "Price_Per_Sqm_EGP" in df.columns

    def test_summary_stats(self):
        from data.land_database import summary_stats
        stats = summary_stats()
        assert stats["total_lands"] == 10
        assert stats["total_value_egp"] > 0
        assert stats["auction_lands"] > 0

    def test_enriched_fields(self):
        """Verify new geological/infrastructure fields exist."""
        from data.land_database import get_all_lands
        lands = get_all_lands()
        for land in lands:
            assert "Bearing_Capacity_kPa" in land
            assert "Seismic_Risk" in land
            assert "Electricity_Capacity_MW" in land
            assert "Nearest_Airport_km" in land
            assert "Historical_Price_1Y_Ago" in land
            assert "Market_Trend" in land
            assert "Development_Cost_Per_Sqm" in land
            assert "Total_Price_EGP" in land

    def test_get_auction_lands(self):
        from data.land_database import get_auction_lands
        auctions = get_auction_lands()
        assert len(auctions) > 0
        assert all(land["Investment_Status"] == "Public Auction" for land in auctions)


class TestRAGService:
    """Tests for the RAG search engine."""

    def test_extract_intent_usage(self):
        from rag.search_engine import extract_intent
        intent = extract_intent("I need industrial land in Cairo")
        assert intent["target_usage"] == "Industrial"
        assert intent["target_gov"] == "Cairo"

    def test_extract_intent_financial(self):
        from rag.search_engine import extract_intent
        intent = extract_intent("What is the ROI of agricultural land")
        assert intent["is_financial_query"] is True

    def test_extract_intent_prediction(self):
        from rag.search_engine import extract_intent
        intent = extract_intent("Predict the price of this land in 6 months")
        assert intent["is_prediction_query"] is True

    def test_extract_intent_geological(self):
        from rag.search_engine import extract_intent
        intent = extract_intent("What is the seismic risk and soil type?")
        assert intent["is_geological_query"] is True

    def test_extract_intent_infrastructure(self):
        from rag.search_engine import extract_intent
        intent = extract_intent("Does it have electricity and fiber optic?")
        assert intent["is_infrastructure_query"] is True

    def test_search_lands(self):
        from rag.search_engine import search_lands
        results = search_lands("industrial land near port", top_k=3)
        assert len(results) > 0
        assert isinstance(results[0], tuple)
        land, score = results[0]
        assert score > 0

    def test_proactive_match(self):
        from rag.search_engine import proactive_match
        results = proactive_match(
            target_usage="Industrial",
            min_area=100_000,
            max_price_per_sqm=5000,
            required_utilities=["Gas"],
        )
        assert len(results) > 0
        assert results[0]["Compatibility_Percent"] >= results[-1]["Compatibility_Percent"]

    def test_format_context(self):
        from rag.search_engine import format_context_for_llm, search_lands
        results = search_lands("residential in Cairo")
        context = format_context_for_llm(results)
        assert "RETRIEVED LAND RECORDS" in context
        assert "EG-CAI" in context

    def test_filter_by_usage(self):
        from rag.search_engine import filter_lands_by_usage
        industrial = filter_lands_by_usage("Industrial")
        assert all(land["Allowed_Usage"] == "Industrial" for land in industrial)
        all_lands = filter_lands_by_usage("All")
        assert len(all_lands) == 10


class TestFinancialService:
    """Tests for the financial analysis service."""

    def test_compute_full_analysis(self):
        from data.land_database import get_land_by_id
        from services.financial_service import FinancialService
        land = get_land_by_id("EG-CAI-01")
        analysis = FinancialService.compute_full_analysis(land, investment_horizon=5)
        assert analysis.land_id == "EG-CAI-01"
        assert analysis.roi_pct > 0
        assert len(analysis.cash_flows) == 6  # Year 0 + 5 years
        assert analysis.taxes.registration_fee_egp > 0

    def test_different_usages(self):
        from data.land_database import get_all_lands
        from services.financial_service import FinancialService
        for land in get_all_lands():
            analysis = FinancialService.compute_full_analysis(land, investment_horizon=3)
            assert analysis.roi_pct is not None
            assert analysis.total_investment_egp > 0

    def test_tax_calculation(self):
        from data.land_database import get_land_by_id
        from services.financial_service import FinancialService
        land = get_land_by_id("EG-CAI-01")
        analysis = FinancialService.compute_full_analysis(land)
        expected_reg = land["Total_Area_Sqm"] * land["Price_Per_Sqm_EGP"] * 0.03
        assert abs(analysis.taxes.registration_fee_egp - expected_reg) < 1

    def test_payback_period(self):
        from data.land_database import get_land_by_id
        from services.financial_service import FinancialService
        land = get_land_by_id("EG-CAI-02")  # Large residential, good ROI
        analysis = FinancialService.compute_full_analysis(land, investment_horizon=10)
        assert analysis.payback_years > 0


class TestPredictionService:
    """Tests for the price prediction service."""

    def test_predict_single(self):
        from data.land_database import get_land_by_id
        from services.prediction_service import PredictionService
        land = get_land_by_id("EG-CAI-02")  # Rising Fast
        pred = PredictionService().predict(land, horizon_months=12)
        assert pred.predicted_price_per_sqm > 0
        assert pred.confidence_pct > 0
        assert len(pred.key_drivers) > 0

    def test_predict_all(self):
        from data.land_database import get_all_lands
        from services.prediction_service import PredictionService
        preds = PredictionService().predict_all(get_all_lands())
        assert len(preds) == 10
        assert all(p.predicted_price_per_sqm > 0 for p in preds)

    def test_heatmap_data(self):
        from data.land_database import get_all_lands
        from services.prediction_service import PredictionService
        heatmap = PredictionService().generate_heatmap_data(get_all_lands())
        assert len(heatmap) == 10
        assert all("lat" in h and "intensity" in h for h in heatmap)

    def test_rising_fast_land(self):
        """Lands with 'Rising Fast' trend should have higher predictions."""
        from data.land_database import get_land_by_id
        from services.prediction_service import PredictionService
        land = get_land_by_id("EG-CAI-02")  # Rising Fast
        pred = PredictionService().predict(land)
        assert pred.predicted_change_pct > 0


class TestRecommendationEngine:
    """Tests for the recommendation engine."""

    def test_generate_recommendations(self):
        from data.land_database import get_all_lands
        from services.recommendation_service import RecommendationEngine
        recs = RecommendationEngine().generate_recommendations(get_all_lands())
        assert len(recs) > 0
        assert recs[0]["action_score"] >= recs[-1]["action_score"]
        assert all("urgency" in r for r in recs)

    def test_urgency_levels(self):
        from data.land_database import get_all_lands
        from services.recommendation_service import RecommendationEngine
        recs = RecommendationEngine().generate_recommendations(get_all_lands())
        urgencies = {r["urgency"] for r in recs}
        assert len(urgencies) > 0


class TestCustomerService:
    """Tests for the customer service system."""

    def test_create_ticket(self):
        from services.customer_service import CustomerServiceSystem
        cs = CustomerServiceSystem()
        ticket = cs.create_ticket("I need help with ROI calculation")
        assert ticket.ticket_id.startswith("TK-")
        assert ticket.status.value == "Open"

    def test_auto_escalation(self):
        from services.customer_service import CustomerServiceSystem
        cs = CustomerServiceSystem()
        ticket = cs.create_ticket("I need to speak to a human agent about a legal issue")
        assert ticket.auto_escalated is True
        assert ticket.status.value == "Escalated to Human Agent"

    def test_resolve_ticket(self):
        from services.customer_service import CustomerServiceSystem
        cs = CustomerServiceSystem()
        ticket = cs.create_ticket("test query")
        cs.resolve_ticket(ticket.ticket_id, "Issue resolved")
        assert ticket.status.value == "Resolved"

    def test_satisfaction(self):
        from services.customer_service import CustomerServiceSystem
        cs = CustomerServiceSystem()
        ticket = cs.create_ticket("test")
        cs.resolve_ticket(ticket.ticket_id, "done")
        assert cs.record_satisfaction(ticket.ticket_id, 4) is True
        stats = cs.get_satisfaction_stats()
        assert stats["avg_score"] == 4.0

    def test_dashboard_metrics(self):
        from services.customer_service import CustomerServiceSystem
        cs = CustomerServiceSystem()
        cs.create_ticket("q1")
        cs.create_ticket("I need legal help")
        metrics = cs.get_dashboard_metrics()
        assert metrics["total_tickets"] == 2
        assert metrics["escalated_tickets"] >= 1


class TestFeasibilityService:
    """Tests for the feasibility report generator."""

    def test_generate_report(self):
        from data.land_database import get_land_by_id
        from services.feasibility_service import FeasibilityReportService
        land = get_land_by_id("EG-SUE-01")
        report = FeasibilityReportService().generate_report(land)
        assert report["land_id"] == "EG-SUE-01"
        assert report["financial"].roi_pct > 0
        assert len(report["risk_assessment"]["risk_items"]) >= 0
        assert len(report["timeline"]) >= 4

    def test_comparison_report(self):
        from data.land_database import get_all_lands
        from services.feasibility_service import FeasibilityReportService
        report = FeasibilityReportService().generate_comparison_report(get_all_lands()[:3])
        assert report["top_pick"] is not None
        assert len(report["comparison_table"]) == 3


class TestETLService:
    """Tests for the ETL service."""

    def test_ingest_json(self):
        from services.etl_service import ETLService
        etl = ETLService()
        json_data = '[{"Land_ID":"TEST-01","Governorate":"Test","Region_City":"TestCity",' \
                   '"Latitude":30.0,"Longitude":31.0,"Total_Area_Sqm":10000,' \
                   '"Price_Per_Sqm_EGP":1000,"Allowed_Usage":"Industrial"}]'
        result = etl.ingest_json(json_data)
        assert len(result["records"]) == 1
        assert result["stats"]["successful"] == 1

    def test_validation_missing_field(self):
        from services.etl_service import ETLService
        etl = ETLService()
        json_data = '[{"Land_ID":"TEST-02","Governorate":"Test"}]'  # Missing required fields
        result = etl.ingest_json(json_data)
        assert len(result["records"]) == 0
        assert len(result["errors"]) > 0

    def test_validation_bad_coords(self):
        from services.etl_service import ETLService
        etl = ETLService()
        json_data = '[{"Land_ID":"TEST-03","Governorate":"Test","Region_City":"Test",' \
                   '"Latitude":50.0,"Longitude":31.0,"Total_Area_Sqm":1000,' \
                   '"Price_Per_Sqm_EGP":100,"Allowed_Usage":"Industrial"}]'
        result = etl.ingest_json(json_data)
        assert len(result["errors"]) > 0  # Latitude outside Egypt bounds


class TestPydanticModels:
    """Tests for Pydantic domain models."""

    def test_land_record(self):
        from data.land_database import get_land_by_id
        from models.land import LandRecord
        raw = get_land_by_id("EG-CAI-01")
        record = LandRecord.from_raw_dict(raw)
        assert record.land_id == "EG-CAI-01"
        assert record.total_price_egp > 0

    def test_investor_criteria(self):
        from models.investor import InvestorCriteria
        criteria = InvestorCriteria(
            target_usage="Industrial",
            min_area_sqm=100_000,
            max_price_per_sqm=5000,
            required_utilities=["Gas", "Fiber-Optic"],
        )
        assert "Industrial" in criteria.to_summary_text()

    def test_financial_analysis_model(self):
        from models.financial import CashFlowEntry
        cf = CashFlowEntry(year=0, net_cash_flow=-100000, cumulative_cash_flow=-100000)
        assert cf.year == 0

    def test_support_ticket(self):
        from models.ticket import SupportTicket, TicketStatus
        ticket = SupportTicket(ticket_id="TK-TEST", user_query="test")
        ticket.escalate("test reason")
        assert ticket.status == TicketStatus.ESCALATED
        ticket.resolve("resolved")
        assert ticket.status == TicketStatus.RESOLVED

    def test_price_prediction_model(self):
        from models.prediction import PricePrediction
        pred = PricePrediction(
            land_id="TEST", governorate="Cairo", region_city="Test",
            current_price_per_sqm=1000, predicted_price_per_sqm=1150,
            predicted_change_pct=15.0, confidence_pct=80.0,
        )
        assert pred.predicted_change_pct == 15.0


class TestGLMService:
    """Tests for the GLM service (mock mode)."""

    def test_chat_mock(self):
        from services.glm_service import GLMService
        glm = GLMService()
        response = glm.chat("Find industrial land", "Some context")
        assert len(response) > 0

    def test_stream_chat_mock(self):
        from services.glm_service import GLMService
        glm = GLMService()
        chunks = list(glm.stream_chat("test query", "context"))
        assert len(chunks) > 0

    def test_input_validation(self):
        from services.glm_service import GLMService
        glm = GLMService()
        # Very long input should raise or be handled
        try:
            glm._validate_input("x" * 600)
            assert False, "Should have raised"
        except ValueError:
            pass

    def test_usage_stats(self):
        from services.glm_service import GLMService
        glm = GLMService()
        stats = glm.get_usage_stats()
        assert "total_tokens" in stats


class TestDensityService:
    """Tests for the Service Density & Clustering service."""

    def test_analyze_new_cairo(self):
        """EG-CAI-01 (New Cairo) should show HIGH retail saturation."""
        from data.land_database import get_land_by_id
        from models.land import SaturationLevel
        from services.density_service import DensityService

        land = get_land_by_id("EG-CAI-01")
        result = DensityService().analyze(land)

        assert result.retail_entertainment_saturation in (SaturationLevel.HIGH, SaturationLevel.CRITICAL)
        assert result.overall_density_score > 50
        assert len(result.profiles) == 3
        assert result.profiles[0].radius_km == 2.0
        assert result.profiles[2].radius_km == 10.0
        assert result.clustering_verdict != ""

    def test_analyze_toshka(self):
        """EG-ASW-01 (Toshka) should show LOW saturation across all categories."""
        from data.land_database import get_land_by_id
        from models.land import SaturationLevel
        from services.density_service import DensityService

        land = get_land_by_id("EG-ASW-01")
        result = DensityService().analyze(land)

        assert result.retail_entertainment_saturation == SaturationLevel.LOW
        assert result.civic_infrastructure_saturation == SaturationLevel.LOW
        assert result.industrial_infrastructure_saturation == SaturationLevel.LOW
        assert result.overall_density_score < 10

    def test_analyze_10th_of_ramadan(self):
        """EG-SHQ-01 (10th of Ramadan) should show HIGH/CRITICAL industrial saturation."""
        from data.land_database import get_land_by_id
        from models.land import SaturationLevel
        from services.density_service import DensityService

        land = get_land_by_id("EG-SHQ-01")
        result = DensityService().analyze(land)

        assert result.industrial_infrastructure_saturation in (SaturationLevel.HIGH, SaturationLevel.CRITICAL)
        assert len(result.market_gap_analysis) > 0

    def test_gap_analysis_saturated_retail(self):
        """A land with HIGH retail saturation should generate gap recommendations."""
        from models.land import SaturationLevel
        from services.density_service import DensityService

        land = {
            "Land_ID": "TEST-DENSITY",
            "Allowed_Usage": "Industrial",
            "Service_Density_Clusters": [
                {"radius_km": 5, "retail": 15, "civic": 2, "industrial": 1},
            ],
        }
        result = DensityService().analyze(land)

        assert result.retail_entertainment_saturation == SaturationLevel.CRITICAL
        assert len(result.market_gap_analysis) > 0
        # Recommendations should include non-retail alternatives
        rec_usages = [g["recommended_usage"] for g in result.market_gap_analysis]
        assert any("Hospital" in u or "School" in u or "Logistics" in u for u in rec_usages)

    def test_generate_saturation_report(self):
        """Saturation report should be a non-empty string with key sections."""
        from data.land_database import get_land_by_id
        from services.density_service import DensityService

        land = get_land_by_id("EG-CAI-01")
        report = DensityService().generate_saturation_report(land)

        assert "MARKET SATURATION & GAP REPORT" in report
        assert "EG-CAI-01" in report
        assert "SATURATION ASSESSMENT" in report
        assert "CLUSTERING VERDICT" in report
        assert "km" in report

    def test_format_density_for_llm(self):
        """LLM format should be compact and include key metrics."""
        from data.land_database import get_land_by_id
        from services.density_service import DensityService

        land = get_land_by_id("EG-CAI-01")
        formatted = DensityService().format_density_for_llm(land)

        assert "Service Density" in formatted
        assert "Score=" in formatted
        assert "Saturation:" in formatted

    def test_analyze_no_density_data(self):
        """Land without density data should return safe defaults."""
        from models.land import SaturationLevel
        from services.density_service import DensityService

        land = {
            "Land_ID": "TEST-EMPTY",
            "Allowed_Usage": "Residential",
        }
        result = DensityService().analyze(land)

        assert result.overall_density_score == 0.0
        assert result.retail_entertainment_saturation == SaturationLevel.LOW
        assert result.market_gap_analysis == []

    def test_analyze_all(self):
        """analyze_all should return results for all 10 lands."""
        from data.land_database import get_all_lands
        from services.density_service import DensityService

        results = DensityService().analyze_all(get_all_lands())
        assert len(results) == 10
        assert "EG-CAI-01" in results
        assert "EG-ASW-01" in results

    def test_density_in_rag_context(self):
        """Density data should appear in RAG LLM context output."""
        from rag.search_engine import format_context_for_llm, search_lands
        results = search_lands("residential in Cairo")
        context = format_context_for_llm(results)
        assert "Service Density" in context

    def test_density_intent_extraction(self):
        """Queries about saturation/density should trigger is_density_query."""
        from rag.search_engine import extract_intent

        intent = extract_intent("What is the market saturation near this land?")
        assert intent["is_density_query"] is True

        intent2 = extract_intent("Are there many malls nearby?")
        assert intent2["is_density_query"] is True

    def test_density_in_recommendations(self):
        """Recommendations should include density-related scoring fields."""
        from data.land_database import get_all_lands
        from services.recommendation_service import RecommendationEngine

        recs = RecommendationEngine().generate_recommendations(get_all_lands())
        assert len(recs) > 0
        assert "density_score" in recs[0]
        assert "density_verdict" in recs[0]
        assert recs[0]["density_score"] >= 0

    def test_density_in_feasibility_report(self):
        """Feasibility report should include saturation report section."""
        from data.land_database import get_land_by_id
        from services.feasibility_service import FeasibilityReportService

        land = get_land_by_id("EG-SUE-01")
        report = FeasibilityReportService().generate_report(land)

        assert "saturation_report" in report
        assert "density_analysis" in report
        assert "MARKET SATURATION" in report["saturation_report"]

    def test_density_in_prediction(self):
        """Prediction service should factor density into its calculation."""
        from data.land_database import get_land_by_id
        from services.prediction_service import PredictionService

        land = get_land_by_id("EG-CAI-01")
        pred = PredictionService().predict(land)

        # Driver should mention clustering for high-density land
        has_density_driver = any("cluster" in d.lower() for d in pred.key_drivers)
        # EG-CAI-01 has 22 retail + 12 civic + 3 industrial = 37 at 5km
        # This should trigger the positive density driver
        assert has_density_driver

    def test_profile_totals(self):
        """Each RadiusProfile total should equal sum of categories."""
        from data.land_database import get_all_lands
        from services.density_service import DensityService

        results = DensityService().analyze_all(get_all_lands())
        for land_id, analysis in results.items():
            for profile in analysis.profiles:
                expected_total = (
                    profile.retail_entertainment
                    + profile.civic_infrastructure
                    + profile.industrial_infrastructure
                )
                assert profile.total == expected_total, (
                    f"{land_id} @ {profile.radius_km}km: "
                    f"total={profile.total} != {expected_total}"
                )


class TestLogisticsService:
    """Tests for the Logistics & Warehousing service."""

    def test_analyze_sokhna(self):
        """EG-SUE-01 (Sokhna) should have the highest logistics score."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SUE-01")
        result = LogisticsService().analyze(land)

        assert result.accessibility_score > 70
        assert result.rail_freight_access is True
        assert result.container_handling_nearby is True
        assert result.logistics_verdict != ""

    def test_analyze_toshka(self):
        """EG-ASW-01 (Toshka) should have a very low logistics score."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-ASW-01")
        result = LogisticsService().analyze(land)

        assert result.accessibility_score < 20
        assert result.rail_freight_access is False
        assert result.road_quality.value == "Poor"

    def test_analyze_alexandria(self):
        """EG-ALX-01 (Borg El Arab) should have excellent port proximity."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-ALX-01")
        result = LogisticsService().analyze(land)

        assert result.accessibility_score > 60
        assert result.estimated_fuel_cost_per_trip_egp == 800
        assert result.cold_chain_available is True

    def test_analyze_no_logistics_data(self):
        """Land without logistics_meta should return minimal score (road quality default only)."""
        from models.land import RoadQuality
        from services.logistics_service import LogisticsService

        land = {"Land_ID": "TEST-NO-LOG", "Allowed_Usage": "Logistics"}
        result = LogisticsService().analyze(land)

        assert result.accessibility_score < 20  # Only road quality baseline
        assert result.road_quality == RoadQuality.AVERAGE
        assert result.rail_freight_access is False

    def test_generate_logistics_report(self):
        """Report should contain key sections."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SUE-01")
        report = LogisticsService().generate_logistics_report(land)

        assert "LOGISTICS & FREIGHT ANALYSIS" in report
        assert "EG-SUE-01" in report
        assert "TRANSPORTATION ACCESS" in report
        assert "FUEL CONSUMPTION ENGINE" in report
        assert "VERDICT" in report

    def test_format_logistics_for_llm(self):
        """LLM format should be compact."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SHQ-01")
        formatted = LogisticsService().format_logistics_for_llm(land)

        assert "Logistics Score:" in formatted
        assert "Highway" in formatted

    def test_rank_for_logistics(self):
        """Sokhna should rank #1 for logistics suitability."""
        from data.land_database import get_all_lands
        from services.logistics_service import LogisticsService

        ranked = LogisticsService().rank_for_logistics(get_all_lands(), top_k=3)
        assert ranked[0]["land_id"] == "EG-SUE-01"
        assert ranked[0]["accessibility_score"] >= ranked[1]["accessibility_score"]
        assert all(len(r["highlights"]) > 0 for r in ranked)

    def test_logistics_intent_extraction(self):
        """Queries about freight/shipping should trigger is_logistics_query."""
        from rag.search_engine import extract_intent

        intent = extract_intent("What is the fuel cost for shipping from this land?")
        assert intent["is_logistics_query"] is True

        intent2 = extract_intent("Does it have container handling and cold chain?")
        assert intent2["is_logistics_query"] is True

    def test_logistics_in_rag_context(self):
        """Logistics data should appear in RAG LLM context."""
        from rag.search_engine import format_context_for_llm, search_lands
        results = search_lands("logistics land near port")
        context = format_context_for_llm(results)
        assert "Logistics:" in context

    def test_logistics_in_feasibility_report(self):
        """Feasibility report should include logistics section."""
        from data.land_database import get_land_by_id
        from services.feasibility_service import FeasibilityReportService

        land = get_land_by_id("EG-SUE-01")
        report = FeasibilityReportService().generate_report(land)

        assert "logistics_report" in report
        assert "logistics_analysis" in report
        assert "LOGISTICS & FREIGHT ANALYSIS" in report["logistics_report"]

    def test_analyze_all(self):
        """analyze_all should return results for all 10 lands."""
        from data.land_database import get_all_lands
        from services.logistics_service import LogisticsService

        results = LogisticsService().analyze_all(get_all_lands())
        assert len(results) == 10

    def test_fuel_cost_annual_estimate(self):
        """Report should include annual fuel cost estimate (250 trips)."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-MNF-01")
        report = LogisticsService().generate_logistics_report(land)
        assert "Annual Fuel Cost" in report

    # ── Fleet Maintenance & Road Quality Factor Tests ──

    def test_fleet_maintenance_excellent_roads(self):
        """Excellent roads should yield 0% maintenance overhead."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SUE-01")
        result = LogisticsService().analyze(land)

        assert result.fleet_maintenance is not None
        assert result.fleet_maintenance.road_quality_index.value == "Excellent"
        assert result.fleet_maintenance.maintenance_overhead_pct == 0.0
        assert result.fleet_maintenance.estimated_annual_maintenance_egp is not None
        assert result.fleet_maintenance.estimated_annual_maintenance_egp > 0
        assert len(result.fleet_maintenance.wear_factors) > 0

    def test_fleet_maintenance_poor_roads(self):
        """Poor roads should yield >=50% maintenance overhead."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-ASW-01")
        result = LogisticsService().analyze(land)

        assert result.fleet_maintenance is not None
        assert result.fleet_maintenance.road_quality_index.value == "Poor"
        assert result.fleet_maintenance.maintenance_overhead_pct >= 50.0
        assert any("severe" in f.lower() or "extreme" in f.lower() or "pothole" in f.lower()
                   for f in result.fleet_maintenance.wear_factors)

    def test_fleet_maintenance_cost_scales_with_fleet(self):
        """Poor-road annual cost should exceed Excellent-road annual cost."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        sokhna = LogisticsService().analyze(get_land_by_id("EG-SUE-01"))
        toshka = LogisticsService().analyze(get_land_by_id("EG-ASW-01"))

        assert toshka.fleet_maintenance.estimated_annual_maintenance_egp > \
               sokhna.fleet_maintenance.estimated_annual_maintenance_egp

    # ── Fuel Consumption Engine Tests ──

    def test_fuel_consumption_diesel(self):
        """Standard land without solar grid should use Diesel fuel type."""
        from data.land_database import get_land_by_id
        from models.land import FuelType
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SHQ-01")
        result = LogisticsService().analyze(land)

        assert result.fuel_trip is not None
        assert result.fuel_trip.fuel_type == FuelType.DIESEL
        assert result.fuel_trip.distance_km > 0
        assert result.fuel_trip.consumption_liters > 0
        assert result.fuel_trip.cost_per_trip_egp > 0
        assert result.fuel_trip.cost_per_ton_km_egp > 0
        assert result.fuel_trip.annual_fuel_cost_egp > 0

    def test_fuel_consumption_solar_hybrid(self):
        """SCZone with 100MW dedicated power should trigger Solar-assisted Hybrid."""
        from data.land_database import get_land_by_id
        from models.land import FuelType
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SUE-01")
        result = LogisticsService().analyze(land)

        assert result.fuel_trip is not None
        assert result.fuel_trip.fuel_type == FuelType.HYBRID
        assert result.fuel_trip.solar_savings_pct > 0

    def test_fuel_per_ton_km_sokhna_vs_toshka(self):
        """Sokhna (5km) should have lower per-ton-km cost than Toshka (250km)."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        sokhna = LogisticsService().analyze(get_land_by_id("EG-SUE-01"))
        toshka = LogisticsService().analyze(get_land_by_id("EG-ASW-01"))

        assert sokhna.fuel_trip.cost_per_ton_km_egp < toshka.fuel_trip.cost_per_ton_km_egp

    def test_fuel_no_port_distance(self):
        """Land without port distance should return empty FuelTripEstimate."""
        from services.logistics_service import LogisticsService

        land = {"Land_ID": "TEST-NO-PORT", "Allowed_Usage": "Logistics",
                "logistics_meta": {"road_quality": "Excellent"}}
        result = LogisticsService().analyze(land)

        assert result.fuel_trip is not None
        assert result.fuel_trip.cost_per_trip_egp == 0.0

    # ── Air Freight & Cargo Airport Connectivity Tests ──

    def test_air_freight_sokhna(self):
        """Sokhna should map to Cairo International Airport (Tier-1 Major)."""
        from data.land_database import get_land_by_id
        from models.land import CargoAirportTier
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SUE-01")
        result = LogisticsService().analyze(land)

        assert result.air_freight is not None
        assert result.air_freight.nearest_cargo_airport == "Cairo International Airport"
        assert result.air_freight.airport_tier == CargoAirportTier.TIER_1_MAJOR
        assert result.air_freight.distance_km == 55.0
        assert result.air_freight.trucking_transit_hours > 0
        assert result.air_freight.daily_cargo_capacity_tons == 1200.0
        assert result.air_freight.perishable_export_suitable is True

    def test_air_freight_tier2_regional(self):
        """Borg El Arab should map to Borg El Arab Airport (Tier-2 Regional)."""
        from data.land_database import get_land_by_id
        from models.land import CargoAirportTier
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-ALX-01")
        result = LogisticsService().analyze(land)

        assert result.air_freight is not None
        assert result.air_freight.nearest_cargo_airport == "Borg El Arab Airport"
        assert result.air_freight.airport_tier == CargoAirportTier.TIER_2_REGIONAL
        assert result.air_freight.distance_km == 18.0
        assert result.air_freight.trucking_transit_hours < 1.0

    def test_air_freight_transit_time_calculation(self):
        """Transit time should be distance / speed based on road quality."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        alex = LogisticsService().analyze(get_land_by_id("EG-ALX-01"))
        # 18km / 55 km/h ≈ 0.33h
        assert 0.2 < alex.air_freight.trucking_transit_hours < 0.5

    # ── Rail Freight Integration Tests ──

    def test_rail_freight_high_speed_electric(self):
        """Sokhna SCZone should have High-Speed Electric rail."""
        from data.land_database import get_land_by_id
        from models.land import RailNetworkType
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SUE-01")
        result = LogisticsService().analyze(land)

        assert result.rail_freight is not None
        assert result.rail_freight.rail_access is True
        assert result.rail_freight.network_type == RailNetworkType.HIGH_SPEED_ELECTRIC
        assert result.rail_freight.station_name == "Sokhna SCZone Rail Terminal"
        assert result.rail_freight.station_distance_km == 3.0
        assert result.rail_freight.estimated_tonnage_cost_saving_pct == 40.0
        assert result.rail_freight.heavy_tonnage_viable is True

    def test_rail_freight_conventional(self):
        """10th of Ramadan should have Conventional Freight rail."""
        from data.land_database import get_land_by_id
        from models.land import RailNetworkType
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SHQ-01")
        result = LogisticsService().analyze(land)

        assert result.rail_freight is not None
        assert result.rail_freight.rail_access is True
        assert result.rail_freight.network_type == RailNetworkType.CONVENTIONAL_FREIGHT
        assert result.rail_freight.heavy_tonnage_viable is True

    def test_rail_freight_no_access(self):
        """Toshka should have no rail freight access."""
        from data.land_database import get_land_by_id
        from models.land import RailNetworkType
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-ASW-01")
        result = LogisticsService().analyze(land)

        assert result.rail_freight is not None
        assert result.rail_freight.rail_access is False
        assert result.rail_freight.network_type == RailNetworkType.NONE
        assert result.rail_freight.heavy_tonnage_viable is False

    def test_rail_cost_saving_high_speed_vs_conventional(self):
        """High-Speed Electric rail should show higher savings than Conventional."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        sokhna = LogisticsService().analyze(get_land_by_id("EG-SUE-01"))
        sharqia = LogisticsService().analyze(get_land_by_id("EG-SHQ-01"))

        assert (sokhna.rail_freight.estimated_tonnage_cost_saving_pct >
                sharqia.rail_freight.estimated_tonnage_cost_saving_pct)

    # ── Logistics Feasibility Matrix Tests ──

    def test_feasibility_matrix_structure(self):
        """Matrix should contain all four dimension headers."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SUE-01")
        matrix = LogisticsService().generate_logistics_feasibility_matrix(land)

        assert "LOGISTICS FEASIBILITY MATRIX" in matrix
        assert "Fleet Maintenance" in matrix
        assert "Fuel Consumption" in matrix
        assert "Air Freight" in matrix
        assert "Rail Freight" in matrix
        assert "OVERALL VERDICT" in matrix

    def test_feasibility_matrix_contains_metrics(self):
        """Matrix should contain specific metric values."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SUE-01")
        matrix = LogisticsService().generate_logistics_feasibility_matrix(land)

        assert "Excellent" in matrix
        assert "Diesel" in matrix or "Hybrid" in matrix
        assert "Cairo International Airport" in matrix
        assert "High-Speed Electric" in matrix
        assert "40%" in matrix  # rail cost saving

    def test_feasibility_matrix_in_feasibility_report(self):
        """Feasibility report for logistics land should include the matrix."""
        from data.land_database import get_land_by_id
        from services.feasibility_service import FeasibilityReportService

        land = get_land_by_id("EG-SUE-01")
        report = FeasibilityReportService().generate_report(land)

        assert "logistics_matrix" in report
        assert "LOGISTICS FEASIBILITY MATRIX" in report["logistics_matrix"]
        assert report["logistics_matrix"] != ""

    def test_feasibility_matrix_not_in_residential(self):
        """Feasibility report for residential land should NOT include matrix."""
        from data.land_database import get_land_by_id
        from services.feasibility_service import FeasibilityReportService

        land = get_land_by_id("EG-CAI-01")
        report = FeasibilityReportService().generate_report(land)

        assert report["logistics_matrix"] == ""

    # ── RAG Context Injection Tests ──

    def test_logistics_matrix_in_rag_context(self):
        """Logistics Feasibility Matrix should appear in RAG context for logistics queries."""
        from rag.search_engine import (extract_intent, format_context_for_llm,
                                       search_lands)

        query = "Find logistics warehouse near port with good rail access"
        intent = extract_intent(query)
        results = search_lands(query)
        context = format_context_for_llm(results, intent=intent)

        assert "LOGISTICS FEASIBILITY MATRIX" in context

    def test_no_matrix_for_non_logistics_query(self):
        """Non-logistics queries should NOT trigger matrix in context."""
        from rag.search_engine import (extract_intent, format_context_for_llm,
                                       search_lands)

        query = "Find residential land in Cairo"
        intent = extract_intent(query)
        results = search_lands(query)
        context = format_context_for_llm(results, intent=intent)

        assert "LOGISTICS FEASIBILITY MATRIX" not in context

    def test_logistics_warehouse_intent_flag(self):
        """Queries combining logistics keywords + Logistics usage should set is_logistics_warehouse_query."""
        from rag.search_engine import extract_intent

        intent = extract_intent("I need a logistics warehouse with rail freight access")
        assert intent["is_logistics_warehouse_query"] is True
        assert intent["target_usage"] == "Logistics"

    def test_new_rag_keywords(self):
        """New logistics keywords should trigger is_logistics_query."""
        from rag.search_engine import extract_intent

        intent = extract_intent("What is the air freight connectivity to cargo airport?")
        assert intent["is_logistics_query"] is True

        intent2 = extract_intent("Does this land have high-speed electric rail for heavy tonnage?")
        assert intent2["is_logistics_query"] is True

        intent3 = extract_intent("What is the fleet maintenance overhead due to road quality?")
        assert intent3["is_logistics_query"] is True

    # ── Recommendation Integration Tests ──

    def test_recommendation_includes_rail_signal(self):
        """Logistics/Industrial lands with rail should mention rail in recommendations."""
        from data.land_database import get_all_lands
        from services.recommendation_service import RecommendationEngine

        recs = RecommendationEngine().generate_recommendations(get_all_lands())
        sokhna_recs = [r for r in recs if r["land_id"] == "EG-SUE-01"]
        assert len(sokhna_recs) > 0
        has_rail_signal = any("rail" in reason.lower() and "tonnage" in reason.lower()
                              for reason in sokhna_recs[0]["reasons"])
        assert has_rail_signal

    def test_recommendation_includes_maintenance_signal(self):
        """Lands with Excellent roads should mention zero maintenance overhead."""
        from data.land_database import get_all_lands
        from services.recommendation_service import RecommendationEngine

        recs = RecommendationEngine().generate_recommendations(get_all_lands())
        sokhna_recs = [r for r in recs if r["land_id"] == "EG-SUE-01"]
        assert len(sokhna_recs) > 0
        has_maint_signal = any("maintenance" in reason.lower()
                               for reason in sokhna_recs[0]["reasons"])
        assert has_maint_signal

    # ── Report Structure Tests ──

    def test_logistics_report_includes_new_sections(self):
        """Upgraded report should include all four new sections."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-SUE-01")
        report = LogisticsService().generate_logistics_report(land)

        assert "FLEET MAINTENANCE" in report
        assert "FUEL CONSUMPTION ENGINE" in report
        assert "AIR FREIGHT" in report
        assert "RAIL FREIGHT INTEGRATION" in report

    def test_logistics_report_road_quality_toshka(self):
        """Toshka report should show Poor roads with 52% overhead."""
        from data.land_database import get_land_by_id
        from services.logistics_service import LogisticsService

        land = get_land_by_id("EG-ASW-01")
        report = LogisticsService().generate_logistics_report(land)

        assert "Poor" in report
        assert "+52%" in report

    # ── Auction & Marketplace Tests ──

    def test_auction_models_import(self):
        """Verify auction models can be imported."""
        from models.auction import (AuctionStatus, BidStatus, LeadStatus,
                                    ListingSource)
        assert AuctionStatus.LIVE.value == "Live"
        assert BidStatus.WINNING.value == "Winning"
        assert LeadStatus.NOTARY_VERIFIED.value == "Verified by Notary"
        assert ListingSource.SCOUT_SOURCED.value == "Scout Sourced"

    def test_auction_engine_create_and_bid(self):
        """Test full auction lifecycle: create, register, bid, finalize."""
        from services.auction_service import AuctionEngine

        engine = AuctionEngine()
        auction = engine.create_auction(
            land_id="TEST-001",
            governorate="Cairo",
            region_city="Test City",
            total_area_sqm=10000,
            allowed_usage="Industrial",
            base_price_egp=5_000_000,
        )
        assert auction.auction_id == "AUC-TEST-001"
        assert auction.status.value == "Live"
        assert auction.base_price_egp == 5_000_000

        # Place a bid
        bid, error = engine.place_bid(
            auction_id=auction.auction_id,
            bidder_id="B-001",
            bidder_name="Test Bidder",
            bid_amount_egp=5_200_000,
        )
        assert error == ""
        assert bid.bid_amount_egp == 5_200_000
        assert bid.status.value == "Winning"
        assert auction.current_highest_bid_egp == 5_200_000
        assert auction.bid_count == 1
        assert auction.registered_bidders_count == 1

        # Second bid should outbid first
        bid2, error2 = engine.place_bid(
            auction_id=auction.auction_id,
            bidder_id="B-002",
            bidder_name="Second Bidder",
            bid_amount_egp=5_400_000,
        )
        assert error2 == ""
        assert bid2.status.value == "Winning"
        assert bid.status.value == "Outbid"
        assert auction.registered_bidders_count == 2

    def test_auction_minimum_bid_enforced(self):
        """Bid below minimum should be rejected."""
        from services.auction_service import AuctionEngine

        engine = AuctionEngine()
        auction = engine.create_auction(
            land_id="TEST-002", governorate="Alex", region_city="Borg",
            total_area_sqm=5000, allowed_usage="Logistics",
            base_price_egp=1_000_000, minimum_increment_pct=5.0,
        )
        _, error = engine.place_bid(
            auction_id=auction.auction_id,
            bidder_id="B-003", bidder_name="Low Bidder",
            bid_amount_egp=1_000_000,  # Exactly base, needs +5%
        )
        assert "at least" in error.lower() or "must be" in error.lower()

    def test_commission_calculator_direct_sale(self):
        """Test fee breakdown for direct sale without scout."""
        from services.auction_service import CommissionCalculator

        bd = CommissionCalculator.compute_breakdown(
            total_value_egp=10_000_000,
            land_id="TEST-DIR",
            is_auction=False,
            scout_eligible=False,
        )
        assert bd.total_transaction_value_egp == 10_000_000
        assert bd.platform_commission_egp == 250_000  # 2.5%
        assert bd.scout_fee_egp == 0
        assert bd.real_estate_disposal_tax_egp == 250_000  # 2.5%
        assert bd.registration_notary_fee_egp == 300_000  # 3.0%
        assert bd.stamp_duty_egp == 50_000  # 0.5%
        assert bd.total_government_duties_egp == 600_000
        assert bd.seller_net_proceeds_egp == 10_000_000 - 250_000 - 600_000
        assert bd.buyer_total_cost_egp == 10_000_000 + 600_000

    def test_commission_calculator_with_scout(self):
        """Test fee breakdown with scout sourcing fee."""
        from services.auction_service import CommissionCalculator

        bd = CommissionCalculator.compute_breakdown(
            total_value_egp=10_000_000,
            land_id="TEST-SCOUT",
            is_auction=True,
            scout_name="Ahmed Mansour",
            scout_eligible=True,
        )
        assert bd.scout_fee_egp == 150_000  # 1.5%
        assert bd.scout_name == "Ahmed Mansour"
        total_deductions = 250_000 + 150_000 + 600_000
        assert bd.seller_net_proceeds_egp == 10_000_000 - total_deductions

    def test_commission_calculator_format_table(self):
        """Test table formatting returns correct structure."""
        from services.auction_service import CommissionCalculator

        bd = CommissionCalculator.compute_breakdown(total_value_egp=5_000_000)
        rows = CommissionCalculator.format_breakdown_table(bd)
        assert len(rows) >= 8
        assert "SELLER" in rows[0]["Party / Item"]
        assert "Platform" in rows[1]["Party / Item"]
        assert any("BUYER" in r["Party / Item"] for r in rows)

    def test_land_sourcing_workflow(self):
        """Test full scout lead lifecycle: submit -> upload -> verify."""
        from models.auction import LeadStatus
        from services.auction_service import LandSourcingService

        svc = LandSourcingService()
        lead = svc.submit_lead(
            scout_id="S-001", scout_name="Test Scout",
            governorate="Suez", region_city="Sokhna",
            estimated_area_sqm=50000, estimated_price_per_sqm_egp=3000,
            description="Test lead for logistics land",
        )
        assert lead.status.value == "Submitted"
        assert lead.legal_document_uploaded is False
        assert lead.scout_fee_eligible is False

        # Upload documents
        lead2 = svc.upload_legal_documents(lead.lead_id)
        assert lead2.legal_document_uploaded is True
        assert lead2.status.value == "Documents Uploaded"

        # Verify with notary
        lead3 = svc.verify_with_notary(lead.lead_id, "NE-SUE-2026-00123")
        assert lead3.verified_by_notary is True
        assert lead3.notary_reference_number == "NE-SUE-2026-00123"
        assert lead3.scout_fee_eligible is True
        assert lead3.status.value == "Verified by Notary"
        assert lead3.status == LeadStatus.NOTARY_VERIFIED

    def test_land_sourcing_stats(self):
        """Test sourcing service stats."""
        from services.auction_service import LandSourcingService

        svc = LandSourcingService()
        stats = svc.get_lead_stats()
        assert "total_leads" in stats
        assert "notary_verified" in stats

    def test_land_database_marketplace_fields(self):
        """Verify new marketplace fields exist on all land records."""
        from data.land_database import get_all_lands

        lands = get_all_lands()
        for land in lands:
            assert "listing_source" in land
            assert "scout_fee_eligible" in land
            assert "legal_document_uploaded" in land
            assert "verified_by_notary" in land
            assert "scout_name" in land

    def test_scout_sourced_lands(self):
        """Verify scout-sourced lands have correct fields."""
        from data.land_database import get_all_lands

        lands = get_all_lands()
        scout_lands = [land for land in lands if land.get("listing_source") == "Scout Sourced"]
        assert len(scout_lands) >= 2
        for land in scout_lands:
            assert land.get("scout_name") is not None
            assert land.get("scout_fee_eligible") is True
            assert land.get("notary_reference") is not None

    def test_rag_auction_intent(self):
        """Test RAG intent extraction for auction queries."""
        from rag.search_engine import extract_intent

        intent = extract_intent("show me auction lands with current bids")
        assert intent["is_auction_query"] is True

        intent2 = extract_intent("what is the fee breakdown for this land")
        assert intent2["is_fee_breakdown_query"] is True

        intent3 = extract_intent("show logistics warehouse near port")
        assert intent3["is_auction_query"] is False
        assert intent3["is_fee_breakdown_query"] is False

    def test_rag_fee_breakdown_context(self):
        """Test that fee breakdown is generated for fee queries."""
        from data.land_database import get_land_by_id
        from rag.search_engine import _generate_fee_breakdown_inline

        land = get_land_by_id("EG-CAI-01")
        result = _generate_fee_breakdown_inline(land)
        assert "FINANCIAL BREAKDOWN TABLE" in result
        assert "Platform Commission" in result
        assert "SELLER NET" in result

    def test_rag_auction_status_context(self):
        """Test auction status inline for auction lands."""
        from data.land_database import get_land_by_id
        from rag.search_engine import _format_auction_status_inline

        land = get_land_by_id("EG-CAI-01")
        result = _format_auction_status_inline(land)
        assert result == ""  # Direct sale, not auction

        auction_land = get_land_by_id("EG-CAI-02")
        result2 = _format_auction_status_inline(auction_land)
        assert "AUCTION STATUS" in result2
        assert "2026-08-15" in result2