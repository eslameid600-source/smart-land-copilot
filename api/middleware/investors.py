"""
Investor API Router
GET  /api/investors/profile              — get investor profile
GET  /api/investors/wallet               — full wallet dashboard
POST /api/investors/deposit              — deposit to wallet
POST /api/investors/redeem-points        — redeem loyalty points
GET  /api/investors/incentives/preview   — preview discounts for amount
GET  /api/investors/loyalty/history      — points transaction history
"""

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from purchase_module.auth import require_role
from purchase_module.database import get_db
from purchase_module.schemas import (
    IncentivePreviewResponse,
    InvestorProfileResponse,
    InvestorWalletResponse,
    LoyaltyRedeemRequest,
    LoyaltyRedeemResponse,
    WalletDepositRequest,
)
from purchase_module.services.incentive_service import IncentiveService
from purchase_module.services.investor_service import InvestorService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/investors", tags=["Investors"])


@router.get(
    "/profile",
    response_model=InvestorProfileResponse,
    summary="Get investor profile",
)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Buyer/Investor")),
):
    """Return the authenticated investor's profile."""
    svc = InvestorService(db)
    return await svc.get_profile(user["sub"])


@router.get(
    "/wallet",
    response_model=InvestorWalletResponse,
    summary="Full wallet dashboard",
)
async def get_wallet(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Buyer/Investor")),
):
    """
    Complete wallet view: balance, owned lands, recent transactions,
    loyalty points, and available discounts.
    """
    svc = InvestorService(db)
    return await svc.get_wallet_view(user["sub"])


@router.post(
    "/deposit",
    response_model=InvestorProfileResponse,
    summary="Deposit funds to wallet",
    status_code=status.HTTP_200_OK,
)
async def deposit(
    body: WalletDepositRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Buyer/Investor")),
):
    """
    Deposit funds into the investor's wallet.
    In production, this would trigger a real payment gateway call.
    Here it directly credits the wallet (simulating external confirmation).
    """
    svc = InvestorService(db)
    try:
        return await svc.deposit_to_wallet(user["sub"], body.amount_egp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/redeem-points",
    response_model=LoyaltyRedeemResponse,
    summary="Redeem loyalty points for a discount",
)
async def redeem_points(
    body: LoyaltyRedeemRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Buyer/Investor")),
):
    """
    Redeem loyalty points. 5 points = 500 EGP discount.
    Points must be in multiples of 5.
    """
    svc = InvestorService(db)
    try:
        return await svc.redeem_loyalty_points(user["sub"], body.points)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/incentives/preview",
    response_model=IncentivePreviewResponse,
    summary="Preview available incentives for a purchase amount",
)
async def preview_incentives(
    amount: Decimal = Query(..., gt=0, description="Purchase amount in EGP"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Buyer/Investor")),
):
    """
    Calculate all available discounts (repeat-buyer + loyalty points)
    for a prospective purchase. Read-only — does not modify any state.
    """
    svc = IncentiveService(db)
    return await svc.preview(user["sub"], amount)


@router.get(
    "/loyalty/history",
    summary="Loyalty points transaction history",
)
async def loyalty_history(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Buyer/Investor")),
):
    """Return the loyalty points earn/redeem log for the investor."""
    svc = IncentiveService(db)
    return await svc.get_loyalty_history(user["sub"], limit=limit)