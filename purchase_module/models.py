"""purchase_module.models — facade re-exporting ORM models from core.account.models.

Also exports the InvestorProfile dataclass which is used by
core/account/incentive_service.py and the test files.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from core.account.models import (  # noqa: F401
    Base,
    User,
    Investor,
    Landowner,
    OwnedLand,
    Broker,
    BrokerAssignment,
    BrokerTransaction,
    LandDocument,
    LandGPSLog,
    WalletTransaction,
    LandownerTransaction,
    Land,
    Transaction,
    InvestmentHistory,
    LandCommissionSettings,
    LoyaltyPointsLog,
    PaymentTransaction,
)


@dataclass
class InvestorProfile:
    """Aggregate investor profile used by the incentive service.

    Wraps the wallet + investment summary + loyalty state
    so the service can reason about a single object.
    """

    user_id: str
    wallet_balance_egp: float = 0.0
    total_lands_purchased: int = 0
    total_spent_egp: float = 0.0
    loyalty_points: int = 0
    discount_rate_pct: float = 0.0
    is_repeat_buyer: bool = False
    preferred_governorates: List[str] = field(default_factory=list)
    preferred_usages: List[str] = field(default_factory=list)
    watchlist: List[str] = field(default_factory=list)
    portfolio: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None


__all__ = [
    "Base",
    "User",
    "Investor",
    "Landowner",
    "OwnedLand",
    "Broker",
    "BrokerAssignment",
    "BrokerTransaction",
    "LandDocument",
    "LandGPSLog",
    "WalletTransaction",
    "LandownerTransaction",
    "Land",
    "Transaction",
    "InvestmentHistory",
    "LandCommissionSettings",
    "LoyaltyPointsLog",
    "PaymentTransaction",
    "InvestorProfile",
]
