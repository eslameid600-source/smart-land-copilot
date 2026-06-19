"""
Smart Land Management Copilot — Feasibility Report Generator
=============================================================
Generates structured mini-feasibility reports for land investments.
"""

from typing import Dict, List, Optional

from services.financial_service import FinancialService
from services.prediction_service import PredictionService
from services.recommendation_service import RecommendationEngine
from services.density_service import DensityService
from services.logistics_service import LogisticsService


class FeasibilityReportService:
    """
    Generates comprehensive feasibility reports combining
    financial analysis, price predictions, market comparison,
    and risk assessment.
    """

    def __init__(self):
        self.fin_svc = FinancialService()
        self.pred_svc = PredictionService()
        self.rec_engine = RecommendationEngine(self.pred_svc)
        self.density_svc = DensityService()
        self.logistics_svc = LogisticsService()

    def generate_report(
        self,
        land: Dict,
        investment_horizon: int = 5,
        include_competitors: bool = True,
    ) -> Dict:
        """
        Generate a complete feasibility report for a single land parcel.

        Returns a structured dict with all sections of the report.
        """
        # ── 1. Executive Summary ──
        total_price = land["Total_Area_Sqm"] * land["Price_Per_Sqm_EGP"]
        executive_summary = (
            f"This report evaluates {land['Land_ID']} located in "
            f"{land['Governorate']} - {land['Region_City']}, covering "
            f"{land['Total_Area_Sqm']:,} sqm of {land['Allowed_Usage'].lower()} land "
            f"priced at {land['Price_Per_Sqm_EGP']:,} EGP/m\u00b2 (total: "
            f"{total_price:,.0f} EGP). The land is available via "
            f"{land['Investment_Status']}."
        )

        # ── 2. Financial Analysis ──
        financial = self.fin_svc.compute_full_analysis(land, investment_horizon)

        # ── 3. Price Prediction ──
        prediction = self.pred_svc.predict(land, horizon_months=12)

        # ── 4. Market Position ──
        market_position = self._analyze_market_position(land)

        # ── 5. Risk Assessment ──
        risk_assessment = self._assess_risks(land)

        # ── 6. Market Saturation & Gap Report ──
        saturation_report = self.density_svc.generate_saturation_report(land)
        density_analysis = self.density_svc.analyze(land)

        # ── 7. Logistics & Freight Analysis ──
        logistics_report = self.logistics_svc.generate_logistics_report(land)
        logistics_analysis = self.logistics_svc.analyze(land)

        # ── 7b. Logistics Feasibility Matrix (for Logistics/Industrial lands) ──
        logistics_matrix = ""
        if land.get("Allowed_Usage") in ("Logistics", "Industrial"):
            logistics_matrix = self.logistics_svc.generate_logistics_feasibility_matrix(land)

        # ── 8. Implementation Timeline ──
        timeline = self._generate_timeline(land)

        # ── 9. Recommendation ──
        recommendation = self._final_recommendation(financial, prediction, risk_assessment, density_analysis, logistics_analysis)

        return {
            "land_id": land["Land_ID"],
            "executive_summary": executive_summary,
            "financial": financial,
            "prediction": prediction,
            "market_position": market_position,
            "risk_assessment": risk_assessment,
            "saturation_report": saturation_report,
            "density_analysis": density_analysis,
            "logistics_report": logistics_report,
            "logistics_analysis": logistics_analysis,
            "logistics_matrix": logistics_matrix,
            "timeline": timeline,
            "recommendation": recommendation,
        }

    def generate_comparison_report(
        self,
        lands: List[Dict],
        investment_horizon: int = 5,
    ) -> Dict:
        """Generate a comparison report for multiple lands."""
        reports = []
        for land in lands:
            r = self.generate_report(land, investment_horizon, include_competitors=False)
            reports.append(r)

        # Sort by ROI
        reports.sort(key=lambda x: x["financial"].roi_pct, reverse=True)

        # Comparison table
        comparison = []
        for r in reports:
            f = r["financial"]
            p = r["prediction"]
            comparison.append({
                "Land_ID": r["land_id"],
                "Total_Investment_EGP": f"{f.total_investment_egp:,.0f}",
                "ROI_%": f"{f.roi_pct}%",
                "IRR_%": f"{f.irr_pct}%",
                "Payback_Years": f"{f.payback_years}",
                "NPV_EGP": f"{f.npv_egp:,.0f}",
                "Predicted_Growth_%": f"{p.predicted_change_pct}%",
                "Recommendation": f.recommendation,
            })

        return {
            "comparison_table": comparison,
            "top_pick": reports[0]["land_id"] if reports else None,
            "reports": reports,
        }

    def format_report_for_llm(self, report: Dict) -> str:
        """Format the full report as text for LLM context injection."""
        f = report["financial"]
        p = report["prediction"]
        risks = report["risk_assessment"]
        tl = report["timeline"]

        lines = [
            "=" * 60,
            f"FEASIBILITY REPORT: {report['land_id']}",
            "=" * 60,
            "",
            "EXECUTIVE SUMMARY",
            "-" * 40,
            report["executive_summary"],
            "",
            "FINANCIAL ANALYSIS",
            "-" * 40,
            f"  Total Investment:  {f.total_investment_egp:,.0f} EGP",
            f"  Annual Revenue:    {f.annual_revenue_egp:,.0f} EGP",
            f"  Annual Net Income: {f.annual_net_income_egp:,.0f} EGP",
            f"  ROI:               {f.roi_pct}%",
            f"  IRR:               {f.irr_pct}%",
            f"  Payback Period:    {f.payback_years} years",
            f"  NPV:               {f.npv_egp:,.0f} EGP",
            f"  Profit Margin:     {f.profit_margin_pct}%",
            f"  Tax & Fees:        {f.taxes.total_acquisition_cost_egp:,.0f} EGP",
            f"  Verdict:           {f.recommendation}",
            "",
            "PRICE PREDICTION (12 months)",
            "-" * 40,
            f"  Current Price:    {p.current_price_per_sqm:,.0f} EGP/m\u00b2",
            f"  Predicted Price:  {p.predicted_price_per_sqm:,.0f} EGP/m\u00b2",
            f"  Change:           {p.predicted_change_pct:+.1f}%",
            f"  Confidence:       {p.confidence_pct}%",
            "",
            "RISK ASSESSMENT",
            "-" * 40,
        ]

        for risk in risks.get("risk_items", []):
            severity = risk["severity"]
            desc = risk["description"]
            mitigation = risk["mitigation"]
            lines.append(f"  [{severity}] {desc}")
            lines.append(f"         Mitigation: {mitigation}")

        lines.extend([
            "",
            "MARKET SATURATION & GAP REPORT",
            "-" * 40,
        ])
        if report.get("saturation_report"):
            lines.append(report["saturation_report"])
        else:
            lines.append("  No density data available for this land.")

        lines.extend([
            "",
            "LOGISTICS & FREIGHT ANALYSIS",
            "-" * 40,
        ])
        if report.get("logistics_report"):
            lines.append(report["logistics_report"])
        else:
            lines.append("  No logistics data available for this land.")

        if report.get("logistics_matrix"):
            lines.extend([
                "",
                "LOGISTICS FEASIBILITY MATRIX",
                "-" * 40,
                report["logistics_matrix"],
            ])

        lines.extend([
            "",
            "IMPLEMENTATION TIMELINE",
            "-" * 40,
        ])
        for phase in tl:
            lines.append(f"  Phase {phase['phase']}: {phase['name']} ({phase['duration']})")
            lines.append(f"    {phase['description']}")

        lines.extend([
            "",
            "FINAL RECOMMENDATION",
            "-" * 40,
            report["recommendation"]["text"],
        ])

        return "\n".join(lines)

    @staticmethod
    def _analyze_market_position(land: Dict) -> Dict:
        """Analyze the land's position relative to market."""
        trend = land.get("Market_Trend", "Stable")
        hist_1y = land.get("Historical_Price_1Y_Ago", land["Price_Per_Sqm_EGP"] * 0.9)
        hist_3y = land.get("Historical_Price_3Y_Ago", land["Price_Per_Sqm_EGP"] * 0.7)
        growth_1y = ((land["Price_Per_Sqm_EGP"] - hist_1y) / hist_1y * 100) if hist_1y else 0
        growth_3y = ((land["Price_Per_Sqm_EGP"] - hist_3y) / hist_3y * 100) if hist_3y else 0

        return {
            "current_trend": trend,
            "price_growth_1y_pct": round(growth_1y, 1),
            "price_growth_3y_pct": round(growth_3y, 1),
            "transaction_volume": land.get("Avg_Transaction_Volume", 0),
            "liquidity": (
                "High" if land.get("Avg_Transaction_Volume", 0) > 10
                else "Medium" if land.get("Avg_Transaction_Volume", 0) > 5
                else "Low"
            ),
        }

    @staticmethod
    def _assess_risks(land: Dict) -> Dict:
        """Generate a structured risk assessment."""
        risk_items = []

        # Geological risks
        if land.get("Seismic_Risk") in ("Moderate", "High"):
            risk_items.append({
                "category": "Geological",
                "severity": "MEDIUM" if land["Seismic_Risk"] == "Moderate" else "HIGH",
                "description": f"Seismic risk: {land['Seismic_Risk']}",
                "mitigation": "Seismic-resistant construction per Egyptian Building Code ECP-201",
            })
        if land.get("Liquefaction_Risk"):
            risk_items.append({
                "category": "Geological",
                "severity": "HIGH",
                "description": "Soil liquefaction potential detected",
                "mitigation": "Deep foundation piles or ground improvement required (estimated +15-20% foundation cost)",
            })
        if land.get("Subsidence_Risk"):
            risk_items.append({
                "category": "Geological",
                "severity": "HIGH",
                "description": "Land subsidence risk in alluvial soil",
                "mitigation": "Geotechnical monitoring system and load distribution design",
            })

        # Environmental risks
        if land.get("Environmental_Permit_Required"):
            risk_items.append({
                "category": "Environmental",
                "severity": "MEDIUM",
                "description": "Environmental Impact Assessment (EIA) permit required",
                "mitigation": "Budget 3-6 months for EIA process; engage environmental consultant early",
            })
        if land.get("Flood_Risk") == "High":
            risk_items.append({
                "category": "Environmental",
                "severity": "HIGH",
                "description": "High flood risk area",
                "mitigation": "Elevated construction, drainage infrastructure, flood insurance",
            })

        # Water quality
        wq = land.get("Water_Quality", "Good")
        if wq in ("Moderate", "Poor"):
            risk_items.append({
                "category": "Environmental",
                "severity": "MEDIUM",
                "description": f"Groundwater quality: {wq}",
                "mitigation": "Water treatment system required; budget for filtration or alternative supply",
            })

        # Market risks
        if land.get("Market_Trend") in ("Stable", "Declining"):
            risk_items.append({
                "category": "Market",
                "severity": "LOW",
                "description": f"Market trend: {land.get('Market_Trend', 'Unknown')}",
                "mitigation": "Negotiate purchase price; consider phased investment approach",
            })

        overall = "LOW"
        if any(r["severity"] == "HIGH" for r in risk_items):
            overall = "HIGH"
        elif any(r["severity"] == "MEDIUM" for r in risk_items):
            overall = "MEDIUM"

        return {
            "overall_risk": overall,
            "risk_count": len(risk_items),
            "risk_items": risk_items,
        }

    @staticmethod
    def _generate_timeline(land: Dict) -> List[Dict]:
        """Generate an implementation timeline based on land type and status."""
        phases = [
            {
                "phase": 1,
                "name": "Due Diligence & Legal",
                "duration": "1-2 months",
                "description": (
                    "Title verification, zoning confirmation (NUCA), "
                    "land survey, and legal contract review"
                ),
            },
        ]

        if land.get("Environmental_Permit_Required"):
            phases.append({
                "phase": 2,
                "name": "Environmental Assessment",
                "duration": "3-6 months",
                "description": "EIA study, public consultation, EEAA approval",
            })

        phases.append({
            "phase": len(phases) + 1,
            "name": "Purchase & Registration",
            "duration": "1-2 months",
            "description": (
                "Final price negotiation, sale agreement, "
                "registration at Land Registry, tax payment"
            ),
        })

        phases.append({
            "phase": len(phases) + 1,
            "name": "Infrastructure & Development",
            "duration": "6-18 months",
            "description": (
                "Site preparation, utility connections, "
                "construction or land improvement works"
            ),
        })

        phases.append({
            "phase": len(phases) + 1,
            "name": "Operations & Revenue",
            "duration": "Ongoing",
            "description": (
                "Commence operations (leasing, farming, or selling), "
                "generate revenue and monitor ROI"
            ),
        })

        return phases

    @staticmethod
    def _final_recommendation(financial, prediction, risk_assessment, density_analysis=None, logistics_analysis=None) -> Dict:
        """Generate the final investment recommendation."""
        signals = []

        if financial.roi_pct >= 15:
            signals.append(f"Strong ROI of {financial.roi_pct}%")
        elif financial.roi_pct >= 8:
            signals.append(f"Acceptable ROI of {financial.roi_pct}%")
        else:
            signals.append(f"Weak ROI of {financial.roi_pct}%")

        if prediction.predicted_change_pct > 10:
            signals.append(f"High price appreciation ({prediction.predicted_change_pct}%)")
        elif prediction.predicted_change_pct > 0:
            signals.append(f"Positive price trend (+{prediction.predicted_change_pct}%)")
        else:
            signals.append("Flat or declining price outlook")

        if risk_assessment["overall_risk"] == "LOW":
            signals.append("Low risk profile")
        elif risk_assessment["overall_risk"] == "HIGH":
            signals.append("High risk — requires mitigation")
        else:
            signals.append("Moderate risk — manageable")

        if financial.payback_years <= 3:
            signals.append("Fast payback period")
        elif financial.payback_years <= 5:
            signals.append("Acceptable payback within 5 years")
        else:
            signals.append(f"Long payback of {financial.payback_years} years")

        # Density/saturation signals
        if density_analysis is not None:
            if density_analysis.overall_density_score >= 75:
                signals.append("High density zone — competition risk elevated")
            elif density_analysis.overall_density_score < 20:
                signals.append("Low-density greenfield — first-mover opportunity")
            if density_analysis.market_gap_analysis:
                warning_gaps = [
                    g for g in density_analysis.market_gap_analysis
                    if g.get("current_usage_viable") and "WARNING" in str(g.get("current_usage_viable", ""))
                ]
                if warning_gaps:
                    signals.append("Planned usage falls in a saturated category")
                else:
                    signals.append("No saturation conflicts with planned usage")

        # Logistics signals
        if logistics_analysis is not None:
            if logistics_analysis.accessibility_score >= 70:
                signals.append("Excellent logistics accessibility supports operational efficiency")
            elif logistics_analysis.accessibility_score < 25:
                signals.append("Poor logistics access may inflate operating costs")

        if financial.recommendation.startswith("STRONG"):
            text = (
                f"RECOMMENDATION: INVEST in this land. Key factors: "
                + "; ".join(signals)
                + ". This represents a strong investment opportunity "
                "aligned with Egyptian market dynamics."
            )
        elif financial.recommendation.startswith("BUY"):
            text = (
                f"RECOMMENDATION: CONSIDER investing. Key factors: "
                + "; ".join(signals)
                + ". The investment shows merit but monitor risk factors."
            )
        elif financial.recommendation.startswith("HOLD"):
            text = (
                f"RECOMMENDATION: NEGOTIATE before investing. Key factors: "
                + "; ".join(signals)
                + ". Consider negotiating a lower purchase price to improve returns."
            )
        else:
            text = (
                f"RECOMMENDATION: DO NOT INVEST at current pricing. Key factors: "
                + "; ".join(signals)
                + ". The financial metrics do not support investment at the asking price."
            )

        return {
            "text": text,
            "signals": signals,
            "verdict": financial.recommendation,
        }