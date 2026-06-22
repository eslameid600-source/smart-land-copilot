"""
Pydantic v2 schemas for request/response validation.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(str, Enum):
    FAWRY = "fawry"
    MEEZA = "meeza"
    STRIPE = "stripe"
    WALLET = "wallet"


class WithdrawalMethod(str, Enum):
    BANK_TRANSFER = "bank_transfer"
    FAWRY = "fawry"
    CHECK = "check"


# ──────────────────────────────────────────────
# Transaction Schemas
# ──────────────────────────────────────────────

class TransactionCreate(BaseModel):
    """Input schema for initiating a land purchase payment."""
    land_id: str = Field(..., min_length=1, description="Unique land identifier")
    buyer_id: str = Field(..., min_length=1, description="Buyer user ID")
    seller_id: str = Field(..., min_length=1, description="Seller (owner) user ID")
    amount_egp: Decimal = Field(..., gt=0, description="Total amount in EGP")
    payment_method: PaymentMethod = Field(
        default=PaymentMethod.FAWRY,
        description="Payment gateway to use",
    )
    apply_loyalty: bool = Field(
        default=False,
        description="Whether to apply loyalty points as discount",
    )

    @field_validator("amount_egp", mode="before")
    @classmethod
    def round_amount(cls, v):
        return Decimal(str(v)).quantize(Decimal("0.01"))


class TransactionResponse(BaseModel):
    """Output schema for transaction data."""
    transaction_id: str
    land_id: str
    buyer_id: str
    seller_id: str
    amount_egp: Decimal
    platform_fee_egp: Decimal = Decimal("0")
    tax_amount_egp: Decimal = Decimal("0")
    discount_applied_egp: Decimal = Decimal("0")
    net_amount_egp: Decimal = Decimal("0")
    status: TransactionStatus
    payment_method: PaymentMethod
    gateway_ref: Optional[str] = None
    gateway_message: Optional[str] = None
    payment_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TransactionConfirmRequest(BaseModel):
    """Input for confirming/completing a payment via webhook."""
    transaction_id: str
    gateway_ref: str
    success: bool = True
    gateway_message: Optional[str] = None


class TransactionHistoryResponse(BaseModel):
    """Paginated transaction history."""
    page: int
    per_page: int
    total: int
    pages: int
    transactions: List[TransactionResponse]

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────
# Investor Schemas
# ──────────────────────────────────────────────

class InvestorProfileResponse(BaseModel):
    """Investor profile data returned to the user."""
    user_id: str
    wallet_balance_egp: Decimal
    loyalty_points: int
    total_invested_egp: Decimal
    total_purchases: int
    successful_purchases: int
    registration_discount_pct: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


class InvestorWalletResponse(BaseModel):
    """Full investor wallet view."""
    profile: InvestorProfileResponse
    owned_lands: List[dict]
    recent_transactions: List[TransactionResponse]
    available_loyalty_discount_egp: Decimal
    is_repeat_buyer: bool

    model_config = {"from_attributes": True}


class WalletDepositRequest(BaseModel):
    """Request to deposit funds into investor wallet."""
    amount_egp: Decimal = Field(..., gt=0, le=50_000_000)
    payment_method: PaymentMethod = PaymentMethod.FAWRY


class LoyaltyRedeemRequest(BaseModel):
    """Request to redeem loyalty points for a discount."""
    points: int = Field(..., ge=5, description="Points to redeem (min 5)")


class LoyaltyRedeemResponse(BaseModel):
    """Result of a loyalty points redemption."""
    points_redeemed: int
    discount_egp: Decimal
    remaining_points: int


class IncentivePreviewResponse(BaseModel):
    """Preview of all available incentives for a purchase."""
    repeat_buyer_discount_pct: Decimal
    repeat_buyer_discount_egp: Decimal
    loyalty_discount_egp: Decimal
    total_discount_egp: Decimal
    points_to_earn: int
    final_price_egp: Decimal
    is_repeat_buyer: bool
    available_loyalty_points: int


# ──────────────────────────────────────────────
# Landowner Schemas
# ──────────────────────────────────────────────

class LandownerProfileResponse(BaseModel):
    """Landowner profile data."""
    user_id: str
    wallet_balance_egp: Decimal
    total_earnings_egp: Decimal
    total_withdrawn_egp: Decimal
    lands_for_sale: int
    lands_sold: int
    withdrawal_method: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LandownerDashboardResponse(BaseModel):
    """Full landowner dashboard view."""
    profile: LandownerProfileResponse
    listed_lands: List[dict]
    sales_report: dict


class WithdrawalRequest(BaseModel):
    """Request to withdraw earnings."""
    amount_egp: Decimal = Field(..., gt=0)
    withdrawal_method: WithdrawalMethod
    bank_account_ref: Optional[str] = Field(
        default=None, description="Required for bank_transfer"
    )

    @field_validator("bank_account_ref")
    @classmethod
    def bank_ref_required_for_transfer(cls, v, info):
        method = info.data.get("withdrawal_method")
        if method == WithdrawalMethod.BANK_TRANSFER and not v:
            raise ValueError("bank_account_ref is required for bank_transfer")
        return v


class WithdrawalResponse(BaseModel):
    """Result of a withdrawal request."""
    amount_withdrawn_egp: Decimal
    remaining_balance_egp: Decimal
    withdrawal_method: str
    status: str


# ──────────────────────────────────────────────
# Auth Schemas
# ──────────────────────────────────────────────

class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str = Field(..., description="User ID")
    role: str = Field(default="Buyer/Investor")
    exp: int
    iat: int


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"