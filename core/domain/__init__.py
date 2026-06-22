"""core.domain — facade package re-exporting entities + verification service."""

# Re-export commonly used Pydantic-style entities
# These are defined inline so files that import them keep working.

from typing import Any, Optional

from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """Generic API response envelope."""
    success: bool = True
    message: str = ""
    data: Optional[Any] = None


class HealthResponse(BaseModel):
    """Health-check response."""
    status: str = "ok"
    version: str = "1.0.0"


class InvestorCreateRequest(BaseModel):
    """Payload for creating an investor."""
    user_id: str
    full_name: str = ""
    initial_deposit_egp: float = 0.0


class LandownerCreateRequest(BaseModel):
    """Payload for creating a landowner."""
    user_id: str
    full_name: str = ""
    default_commission_pct: float = 2.5


class LoyaltyRedeemRequest(BaseModel):
    """Payload for redeeming loyalty points."""
    user_id: str
    points: int = Field(..., ge=100)


class WalletDepositRequest(BaseModel):
    """Payload for depositing into a wallet."""
    user_id: str
    amount_egp: float = Field(..., gt=0)
    payment_gateway: str = "wallet"


class OwnershipTransferRequest(BaseModel):
    """Payload for transferring land ownership."""
    land_id: str
    buyer_id: str
    commission_pct: Optional[float] = None
    payment_gateway: str = "wallet"


class OwnershipTransferResult(BaseModel):
    """Result of an ownership transfer."""
    success: bool
    land_id: str
    seller_id: str
    buyer_id: str
    sale_price_egp: float
    commission_egp: float
    loyalty_points_earned: int
    new_owner_id: str
    transaction_id: str
    transferred_at: str
    message_ar: str


class LandVerificationService:
    """Stub land verification service — used by core.account.broker_service."""

    def __init__(self, session=None):
        self.session = session

    async def verify_land(self, land_id: str) -> bool:
        return True


def get_all_lands() -> list:
    """Stub: returns the in-memory land catalog as a list."""
    try:
        from api.routes.account_store import lands_catalog_global
        return list(lands_catalog_global.values())
    except Exception:
        return []


__all__ = [
    "APIResponse",
    "HealthResponse",
    "InvestorCreateRequest",
    "LandownerCreateRequest",
    "LoyaltyRedeemRequest",
    "WalletDepositRequest",
    "OwnershipTransferRequest",
    "OwnershipTransferResult",
    "LandVerificationService",
    "get_all_lands",
]
