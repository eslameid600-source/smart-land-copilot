"""
Smart Land Management Copilot — Financial Analysis Service
============================================================
Computes ROI, IRR, NPV, payback period, and generates
detailed cash flow projections for Egyptian land investments.
Includes Egyptian tax and fee calculations.
"""

import math
from typing import List, Dict, Optional

from models.financial import (
    FinancialAnalysis, TaxBreakdown, CashFlowEntry,
)
from models.land import LandRecord


class FinancialService:
    """Service for computing full financial analysis of land investments."""

    # ── Egyptian Tax Rates (2024/2025) ──
    LAND_REGISTRATION_FEE_PCT = 3.0
    STAMP_DUTY_PCT = 0.5
    NOTARY_FEE = 5000.0
    LEGAL_REVIEW_FEE = 20000.0
    SURVEY_FEE = 15000.0

    # ── Revenue assumptions by usage type (EGP/sqm/year) ──
    REVENUE_RATES: Dict[str, float] = {
        "Residential": 2500.0,    # Rental income or unit sale value
        "Industrial": 800.0,      # Warehouse/factory lease rate
        "Logistics": 600.0,       # Warehouse/logistics lease
        "Agricultural": 150.0,    # Crop yield value per sqm
    }

    # ── Operating cost as % of revenue ──
    OPEX_RATIOS: Dict[str, float] = {
        "Residential": 0.25,
        "Industrial": 0.35,
        "Logistics": 0.30,
        "Agricultural": 0.45,
    }

    # ── Discount rate for NPV/IRR ──
    DISCOUNT_RATE = 0.15  # 15% cost of capital (Egypt high-yield environment)

    @classmethod
    def compute_full_analysis(
        cls,
        land: Dict,
        investment_horizon: int = 5,
        discount_rate: Optional[float] = None,
    ) -> FinancialAnalysis:
        """
        Generate a complete financial analysis for a land parcel.

        Parameters
        ----------
        land              : Raw land dict from the database
        investment_horizon: Number of years for projection
        discount_rate     : Override the default discount rate
        """
        dr = discount_rate or cls.DISCOUNT_RATE
        land_price = land["Total_Area_Sqm"] * land["Price_Per_Sqm_EGP"]
        area = land["Total_Area_Sqm"]
        price_sqm = land["Price_Per_Sqm_EGP"]
        usage = land["Allowed_Usage"]
        dev_cost_sqm = land.get("Development_Cost_Per_Sqm", 0)

        # ── 1. Tax & Fee Breakdown ──
        registration_fee = land_price * (cls.LAND_REGISTRATION_FEE_PCT / 100)
        stamp_duty = land_price * (cls.STAMP_DUTY_PCT / 100)
        infra_prep = area * dev_cost_sqm * 0.15  # 15% of total dev cost for site prep

        taxes = TaxBreakdown(
            registration_fee_pct=cls.LAND_REGISTRATION_FEE_PCT,
            registration_fee_egp=round(registration_fee, 2),
            stamp_duty_pct=cls.STAMP_DUTY_PCT,
            stamp_duty_egp=round(stamp_duty, 2),
            notary_fees_egp=cls.NOTARY_FEE,
            legal_review_egp=cls.LEGAL_REVIEW_FEE,
            survey_fees_egp=cls.SURVEY_FEE,
            infrastructure_prep_egp=round(infra_prep, 2),
        )
        taxes.total_acquisition_cost_egp = round(
            registration_fee + stamp_duty + cls.NOTARY_FEE
            + cls.LEGAL_REVIEW_FEE + cls.SURVEY_FEE,
            2,
        )
        taxes.total_all_in_cost_egp = round(land_price + taxes.total_acquisition_cost_egp, 2)

        # ── 2. Development Costs ──
        total_dev = area * dev_cost_sqm
        total_investment = taxes.total_all_in_cost_egp + total_dev

        # ── 3. Revenue & Operating Costs ──
        rev_rate = cls.REVENUE_RATES.get(usage, 500.0)
        opex_ratio = cls.OPEX_RATIOS.get(usage, 0.30)

        annual_revenue = area * rev_rate
        annual_opex = annual_revenue * opex_ratio
        annual_net = annual_revenue - annual_opex

        # ── 4. Cash Flow Projection ──
        cash_flows: List[CashFlowEntry] = []
        cumulative = -total_investment  # Year 0: full investment outflow

        # Year 0
        cash_flows.append(CashFlowEntry(
            year=0, revenue=0, operating_cost=0,
            net_cash_flow=-total_investment,
            cumulative_cash_flow=round(cumulative, 2),
            discount_factor=1.0,
            discounted_cash_flow=round(-total_investment, 2),
        ))

        payback_year = investment_horizon
        total_dcf = -total_investment

        for year in range(1, investment_horizon + 1):
            # Revenue growth: 3-12% annually depending on usage
            growth = cls._revenue_growth_rate(usage, year)
            year_revenue = annual_revenue * (1 + growth) ** year
            year_opex = year_revenue * opex_ratio
            year_net = year_revenue - year_opex

            cumulative += year_net
            discount_factor = 1 / (1 + dr) ** year
            year_dcf = year_net * discount_factor
            total_dcf += year_dcf

            if cumulative >= 0 and payback_year == investment_horizon:
                # Linear interpolation for exact payback
                prev_cum = cumulative - year_net
                if prev_cum < 0 and year_net > 0:
                    payback_year = year - 1 + abs(prev_cum) / year_net
                else:
                    payback_year = year

            cash_flows.append(CashFlowEntry(
                year=year,
                revenue=round(year_revenue, 2),
                operating_cost=round(year_opex, 2),
                net_cash_flow=round(year_net, 2),
                cumulative_cash_flow=round(cumulative, 2),
                discount_factor=round(discount_factor, 4),
                discounted_cash_flow=round(year_dcf, 2),
            ))

        # ── 5. Key Metrics ──
        total_net_gain = cumulative + total_investment
        roi = (total_net_gain / total_investment * 100) if total_investment > 0 else 0
        npv = total_dcf
        irr = cls._compute_irr(cash_flows)
        profit_margin = (annual_net / annual_revenue * 100) if annual_revenue > 0 else 0

        # ── 6. Risk Flags ──
        risk_flags = []
        if payback_year > investment_horizon:
            risk_flags.append(f"Payback period ({payback_year:.1f}y) exceeds investment horizon ({investment_horizon}y)")
        if roi < 10:
            risk_flags.append("ROI below 10% threshold for Egyptian market")
        if land.get("Seismic_Risk") == "High":
            risk_flags.append("High seismic risk — additional insurance costs expected")
        if land.get("Flood_Risk") == "High":
            risk_flags.append("High flood risk — drainage infrastructure required")
        if land.get("Environmental_Permit_Required"):
            risk_flags.append("EIA permit required — adds 3-6 months to timeline")

        # ── 7. Recommendation ──
        if roi >= 20 and payback_year <= investment_horizon * 0.6:
            rec = "STRONG BUY — High ROI with fast payback"
        elif roi >= 10 and payback_year <= investment_horizon:
            rec = "BUY — Acceptable returns within horizon"
        elif roi >= 5:
            rec = "HOLD — Marginal returns; consider negotiating price"
        else:
            rec = "PASS — Insufficient financial returns at current price"

        return FinancialAnalysis(
            land_id=land["Land_ID"],
            land_price_egp=land_price,
            total_area_sqm=area,
            price_per_sqm_egp=price_sqm,
            taxes=taxes,
            development_cost_per_sqm=dev_cost_sqm,
            total_development_cost_egp=round(total_dev, 2),
            total_investment_egp=round(total_investment, 2),
            annual_revenue_egp=round(annual_revenue, 2),
            annual_operating_cost_egp=round(annual_opex, 2),
            annual_net_income_egp=round(annual_net, 2),
            roi_pct=round(roi, 2),
            irr_pct=round(irr, 2),
            payback_years=round(payback_year, 1),
            npv_egp=round(npv, 2),
            profit_margin_pct=round(profit_margin, 2),
            cash_flows=cash_flows,
            recommendation=rec,
            risk_flags=risk_flags,
        )

    @staticmethod
    def _revenue_growth_rate(usage: str, year: int) -> float:
        """Annual revenue growth assumptions by usage type."""
        base_rates = {
            "Residential": 0.08,   # 8% rental appreciation
            "Industrial": 0.06,   # 6% industrial lease growth
            "Logistics": 0.10,    # 10% e-commerce driven
            "Agricultural": 0.04, # 4% crop price growth
        }
        base = base_rates.get(usage, 0.05)
        # Slight decay over time
        return base * max(0.7, 1.0 - (year - 1) * 0.05)

    @staticmethod
    def _compute_irr(cash_flows: List[CashFlowEntry], max_iter: int = 1000) -> float:
        """
        Compute IRR using Newton-Raphson method.
        Falls back to 0.0 if it cannot converge.
        """
        if not cash_flows:
            return 0.0

        def npv_at_rate(r: float) -> float:
            return sum(
                cf.discounted_cash_flow * (1 / ((1 + r) ** cf.year))
                if cf.year > 0
                else cf.net_cash_flow
                for cf in cash_flows
            )

        rate = 0.1
        for _ in range(max_iter):
            npv_val = npv_at_rate(rate)
            if abs(npv_val) < 0.01:
                return rate * 100  # Return as percentage
            dnpv = sum(
                -cf.year * cf.net_cash_flow / ((1 + rate) ** (cf.year + 1))
                if cf.year > 0
                else cf.net_cash_flow
                for cf in cash_flows
            )
            if abs(dnpv) < 1e-10:
                break
            rate -= npv_val / dnpv
            rate = max(-0.99, min(rate, 5.0))  # Clamp

        return round(rate * 100, 2)