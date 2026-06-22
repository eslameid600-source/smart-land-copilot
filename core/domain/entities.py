"""core.domain.entities — facade re-exporting common API schemas."""

from core.domain import (  # noqa: F401
    APIResponse,
    HealthResponse,
    InvestorCreateRequest,
    LandownerCreateRequest,
    LoyaltyRedeemRequest,
    WalletDepositRequest,
    OwnershipTransferRequest,
    OwnershipTransferResult,
    LandVerificationService,
    get_all_lands,
)
