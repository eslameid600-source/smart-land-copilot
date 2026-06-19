"""
Payment API Router
POST /api/payments/initiate   — start a purchase payment
POST /api/payments/confirm/{transaction_id} — confirm (webhook)
POST /api/payments/refund/{transaction_id}  — refund
GET  /api/payments/history    — paginated history
GET  /api/payments/status/{transaction_id}  — single status
"""

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from purchase_module.database import get_db
from purchase_module.auth import get_current_user, require_role
from purchase_module.schemas import (
    TransactionCreate,
    TransactionResponse,
    TransactionConfirmRequest,
    TransactionHistoryResponse,
)
from purchase_module.services.payment_service import PaymentService
from purchase_module.services.incentive_service import IncentiveService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["Payments"])


# ──────────────────────────────────────────────
# POST /api/payments/initiate
# ──────────────────────────────────────────────

@router.post(
    "/initiate",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a land purchase payment",
)
async def initiate_payment(
    body: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("Buyer/Investor")),
):
    """
    Start a payment for purchasing a land parcel.
    
    - Validates the buyer matches the token (security).
    - Computes platform fees (1.5%), tax (2.5%), and available discounts.
    - Calls the selected payment gateway and returns a redirect URL.
    """
    if body.buyer_id != user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="buyer_id must match the authenticated user",
        )

    # Compute incentive discount if requested
    discount = Decimal("0")
    if body.apply_loyalty:
        try:
            incentive_svc = IncentiveService(db)
            discount = await incentive_svc.compute_discount(
                user["sub"], body.amount_egp
            )
        except Exception as exc:
            logger.warning("Incentive computation failed, proceeding without: %s", exc)

    try:
        svc = PaymentService(db)
        return await svc.initiate(body, incentive_discount=discount)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ──────────────────────────────────────────────
# POST /api/payments/confirm/{transaction_id}
# ──────────────────────────────────────────────

@router.post(
    "/confirm/{transaction_id}",
    response_model=TransactionResponse,
    summary="Confirm a payment (gateway webhook endpoint)",
)
async def confirm_payment(
    transaction_id: str,
    body: TransactionConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the payment gateway (webhook) or manually to confirm
    a pending transaction as completed or failed.
    On success: marks land as Sold, credits seller wallet, awards loyalty points.
    """
    if body.transaction_id and body.transaction_id != transaction_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="transaction_id in body must match URL parameter",
        )

    try:
        svc = PaymentService(db)
        return await svc.confirm(
            transaction_id=transaction_id,
            gateway_ref=body.gateway_ref,
            success=body.success,
            gateway_message=body.gateway_message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ──────────────────────────────────────────────
# POST /api/payments/refund/{transaction_id}
# ──────────────────────────────────────────────

@router.post(
    "/refund/{transaction_id}",
    response_model=TransactionResponse,
    summary="Refund a completed transaction",
)
async def refund_payment(
    transaction_id: str,
    reason: str = Query("", description="Reason for refund"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Refund a completed purchase. Restores land to Available."""
    try:
        svc = PaymentService(db)
        return await svc.refund(transaction_id, reason=reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ──────────────────────────────────────────────
# GET /api/payments/history
# ──────────────────────────────────────────────

@router.get(
    "/history",
    response_model=TransactionHistoryResponse,
    summary="Get paginated transaction history",
)
async def get_history(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return all transactions for the authenticated user (buyer or seller)."""
    svc = PaymentService(db)
    return await svc.get_history(
        user_id=user["sub"],
        page=page,
        per_page=per_page,
        status_filter=status,
    )


# ──────────────────────────────────────────────
# GET /api/payments/status/{transaction_id}
# ──────────────────────────────────────────────

@router.get(
    "/status/{transaction_id}",
    response_model=TransactionResponse,
    summary="Get transaction status",
)
async def get_status(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return the current status of a single transaction."""
    from purchase_module.models import Transaction
    tx = await db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    from purchase_module.schemas import TransactionResponse, TransactionStatus, PaymentMethod
    return TransactionResponse(
        transaction_id=tx.transaction_id,
        land_id=tx.land_id,
        buyer_id=tx.buyer_id,
        seller_id=tx.seller_id,
        amount_egp=tx.amount_egp,
        platform_fee_egp=tx.platform_fee_egp,
        tax_amount_egp=tx.tax_amount_egp,
        discount_applied_egp=tx.discount_applied_egp,
        net_amount_egp=tx.net_amount_egp,
        status=TransactionStatus(tx.status),
        payment_method=PaymentMethod(tx.payment_method),
        gateway_ref=tx.gateway_ref,
        gateway_message=tx.gateway_message,
        created_at=tx.created_at,
        updated_at=tx.updated_at,
        completed_at=tx.completed_at,
    )