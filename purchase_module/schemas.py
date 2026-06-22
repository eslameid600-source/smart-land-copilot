"""purchase_module.schemas — facade re-exporting API schemas from core.domain.

Also defines payment-related Pydantic schemas that are not in core.domain.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from core.domain import (  # noqa: F401
    APIResponse,
    InvestorCreateRequest,
    LandownerCreateRequest,
    LoyaltyRedeemRequest,
    WalletDepositRequest,
    OwnershipTransferRequest,
    OwnershipTransferResult,
)


# ──────────────────────────────────────────────
# Incentive schemas
# ──────────────────────────────────────────────

class IncentivePreviewResponse(BaseModel):
    """Preview of available discounts and loyalty earnings for a purchase."""

    repeat_buyer_discount_pct: Decimal = Decimal("0")
    repeat_buyer_discount_egp: Decimal = Decimal("0")
    loyalty_discount_egp: Decimal = Decimal("0")
    total_discount_egp: Decimal = Decimal("0")
    points_to_earn: int = 0
    final_price_egp: Decimal = Decimal("0")
    is_repeat_buyer: bool = False
    available_loyalty_points: int = 0


# ──────────────────────────────────────────────
# Profile / Dashboard schemas
# ──────────────────────────────────────────────

class InvestorProfileResponse(BaseModel):
    """Response model for the investor profile endpoint."""

    user_id: str
    full_name: str = ""
    email: Optional[str] = None
    phone_number: Optional[str] = None
    wallet_balance_egp: float = 0.0
    frozen_balance_egp: float = 0.0
    available_balance_egp: float = 0.0
    loyalty_points: int = 0
    total_lands_purchased: int = 0
    total_spent_egp: float = 0.0
    discount_rate_pct: float = 0.0
    is_repeat_buyer: bool = False
    registration_discount_pct: Decimal = Decimal("0")
    successful_purchases: int = 0
    preferred_governorates: list = []
    preferred_usages: list = []
    watchlist: list = []
    portfolio: list = []
    created_at: Optional[str] = None


class LandownerDashboardResponse(BaseModel):
    """Response model for the landowner dashboard endpoint."""

    user_id: str
    full_name: str = ""
    total_lands_listed: int = 0
    active_lands_count: int = 0
    total_lands_sold: int = 0
    total_sales_egp: float = 0.0
    total_commission_earned_egp: float = 0.0
    default_commission_pct: float = 2.5
    lands: list = []
    recent_sales: list = []
    created_at: Optional[str] = None


class LandownerProfileResponse(BaseModel):
    """Response model for the landowner profile endpoint."""

    user_id: str
    full_name: str = ""
    email: Optional[str] = None
    phone_number: Optional[str] = None
    default_commission_pct: float = 2.5
    total_lands_listed: int = 0
    active_lands_count: int = 0
    total_lands_sold: int = 0
    total_sales_egp: float = 0.0
    total_commission_earned_egp: float = 0.0
    created_at: Optional[str] = None


class InvestorWalletResponse(BaseModel):
    """Response model for the investor wallet endpoint."""

    user_id: str
    wallet_balance_egp: float = 0.0
    frozen_balance_egp: float = 0.0
    available_balance_egp: float = 0.0
    loyalty_points: int = 0
    total_lands_purchased: int = 0
    total_spent_egp: float = 0.0
    discount_rate_pct: float = 0.0
    has_repeat_buyer_discount: bool = False
    owned_lands_count: int = 0
    owned_lands: list = []
    recent_transactions: list = []


class LoyaltyRedeemResponse(BaseModel):
    """Response model for the loyalty-redeem endpoint."""

    user_id: str
    points_redeemed: int = 0
    discount_egp: float = 0.0
    remaining_points: int = 0
    new_wallet_balance_egp: Optional[float] = None


class WithdrawalRequest(BaseModel):
    """Request body for a landowner withdrawal."""

    user_id: str
    amount_egp: float = Field(..., gt=0)
    method: str = Field("bank_transfer", description="bank_transfer / fawry / wallet")
    bank_account_id: Optional[str] = None
    notes: Optional[str] = None


class WithdrawalResponse(BaseModel):
    """Response body for a landowner withdrawal."""

    user_id: str
    withdrawal_id: str
    amount_egp: float
    method: str
    status: str = "pending"
    requested_at: Optional[str] = None
    processed_at: Optional[str] = None


# ──────────────────────────────────────────────
# Payment schemas (re-exported from core.payment.models)
# ──────────────────────────────────────────────

from core.payment.models import (  # noqa: F401,E402
    PaymentInitRequest,
    TransactionResponse,
    WebhookCallback,
)


__all__ = [
    "APIResponse",
    "InvestorCreateRequest",
    "LandownerCreateRequest",
    "LoyaltyRedeemRequest",
    "LoyaltyRedeemResponse",
    "WalletDepositRequest",
    "WithdrawalRequest",
    "WithdrawalResponse",
    "OwnershipTransferRequest",
    "OwnershipTransferResult",
    "IncentivePreviewResponse",
    "InvestorProfileResponse",
    "InvestorWalletResponse",
    "LandownerProfileResponse",
    "LandownerDashboardResponse",
    "PaymentInitRequest",
    "TransactionResponse",
    "WebhookCallback",
]
