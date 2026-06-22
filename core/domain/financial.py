"""
Smart Land Management Copilot — Financial Analysis Models
==========================================================
Models for ROI, IRR, cash flow projections, and cost breakdowns.
"""

from typing import List

from pydantic import BaseModel, Field


class CashFlowEntry(BaseModel):
    """Single year cash flow line item."""
    year: int = Field(..., ge=0)
    revenue: float = Field(default=0.0)
    operating_cost: float = Field(default=0.0)
    net_cash_flow: float = Field(default=0.0)
    cumulative_cash_flow: float = Field(default=0.0)
    discount_factor: float = Field(default=1.0)
    discounted_cash_flow: float = Field(default=0.0)


class TaxBreakdown(BaseModel):
    """Egyptian tax and fee breakdown for land acquisition."""
    registration_fee_pct: float = Field(default=3.0, description="Land registration fee %")
    registration_fee_egp: float = Field(default=0.0)
    stamp_duty_pct: float = Field(default=0.5, description="Stamp duty %")
    stamp_duty_egp: float = Field(default=0.0)
    notary_fees_egp: float = Field(default=5000.0, description="Notary public fees")
    legal_review_egp: float = Field(default=20000.0, description="Legal review fees")
    survey_fees_egp: float = Field(default=15000.0, description="Land survey fees")
    infrastructure_prep_egp: float = Field(default=0.0, description="Site preparation and infrastructure")
    total_acquisition_cost_egp: float = Field(default=0.0)
    total_all_in_cost_egp: float = Field(default=0.0)


class FinancialAnalysis(BaseModel):
    """Complete financial analysis for a land investment."""
    land_id: str
    land_price_egp: float
    total_area_sqm: int
    price_per_sqm_egp: float

    # Tax and fees
    taxes: TaxBreakdown = Field(default_factory=TaxBreakdown)

    # Development costs
    development_cost_per_sqm: float = Field(default=0.0)
    total_development_cost_egp: float = Field(default=0.0)
    total_investment_egp: float = Field(default=0.0)

    # Revenue projections
    annual_revenue_egp: float = Field(default=0.0)
    annual_operating_cost_egp: float = Field(default=0.0)
    annual_net_income_egp: float = Field(default=0.0)

    # Key metrics
    roi_pct: float = Field(default=0.0)
    irr_pct: float = Field(default=0.0)
    payback_years: float = Field(default=0.0)
    npv_egp: float = Field(default=0.0)
    profit_margin_pct: float = Field(default=0.0)

    # Cash flow table
    cash_flows: List[CashFlowEntry] = Field(default_factory=list)

    # Recommendation
    recommendation: str = Field(default="")
    risk_flags: List[str] = Field(default_factory=list)