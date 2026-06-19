"""
Smart Land Management Copilot — Price Prediction Model
========================================================
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class PricePrediction(BaseModel):
    """ML-based land price prediction."""
    land_id: str
    governorate: str
    region_city: str
    current_price_per_sqm: float
    predicted_price_per_sqm: float
    predicted_change_pct: float
    confidence_pct: float = Field(default=0.0, ge=0, le=100)
    prediction_horizon_months: int = Field(default=12)
    key_drivers: List[str] = Field(default_factory=list)
    risk_factors: List[str] = Field(default_factory=list)
    recommendation: str = Field(default="")