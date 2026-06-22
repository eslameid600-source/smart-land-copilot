"""
Landowner API Router
GET  /api/landowners/profile      — get landowner profile
GET  /api/landowners/dashboard    — full dashboard with sales report
POST /api/landowners/withdraw     — withdraw earnings
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from purchase_module.auth import require_role
from purchase_module.database import get_db
from purchase_module.schemas import (
    LandownerDashboardResponse,
    LandownerProfileResponse,
    WithdrawalRequest,
    WithdrawalResponse,
)
from purchase_module.services.landowner_service import LandownerService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/landowners", tags=["Landowners"])


@router.get(
    "/profile",
    response_model=LandownerProfileResponse,
    summary="Get landowner profile",
)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Seller/Owner")),
):
    """Return the authenticated landowner's profile."""
    svc = LandownerService(db)
    return await svc.get_profile(user["sub"])


@router.get(
    "/dashboard",
    response_model=LandownerDashboardResponse,
    summary="Full landowner dashboard",
)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Seller/Owner")),
):
    """
    Complete dashboard: profile, listed lands, and detailed sales report
    including total sales, platform fees, taxes, and net earnings.
    """
    svc = LandownerService(db)
    return await svc.get_dashboard(user["sub"])


@router.post(
    "/withdraw",
    response_model=WithdrawalResponse,
    summary="Withdraw earnings from wallet",
)
async def withdraw(
    body: WithdrawalRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Seller/Owner")),
):
    """
    Withdraw funds from the landowner's wallet to their bank account
    or via Fawry. Updates the withdrawal method preference.
    """
    svc = LandownerService(db)
    try:
        return await svc.withdraw(user["sub"], body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))