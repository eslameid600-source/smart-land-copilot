"""
Smart Land Management Copilot V4.0
نقاط نهاية FastAPI — الدفع والمستثمرين وأصحاب الأراضي والحوافز
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Literal, Optional

from infrastructure.database.connection import get_db
from core.payment.models import (
    PaymentInitRequest,
    TransactionResponse,
    WebhookCallback,
    TransactionStatus,
)
from core.payment import service as payment_svc
from core.investor import service as investor_svc
from core.landowner import service as landowner_svc
from core.incentive import service as incentive_svc


# ============================================================
# api/routers/payments.py
# ============================================================

payments_router = APIRouter(
    prefix="/api/v1/payments", tags=["Payments"]
)


@payments_router.post("/initiate", response_model=TransactionResponse)
async def initiate_payment(
    body: PaymentInitRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """بدء عملية دفع جديدة لشراء أرض"""
    buyer_id = request.state.user_id
    try:
        return await payment_svc.initiate_payment(db, buyer_id, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail="فشل الاتصال ببوابة الدفع")


@payments_router.post("/webhook/{gateway}")
async def payment_webhook(
    gateway: str,
    callback: WebhookCallback,
    db: AsyncSession = Depends(get_db),
):
    """استقبال إشعار من بوابة الدفع (Fawry/Stripe/PayPal)"""
    try:
        await payment_svc.handle_webhook(db, gateway, callback)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}


@payments_router.get("/history")
async def get_transaction_history(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """سجل المعاملات المالية للمستخدم الحالي"""
    user_id = request.state.user_id
    txs = await payment_svc.get_transaction_history(
        db, user_id, page, per_page
    )
    return {"page": page, "data": txs}


@payments_router.get("/status/{transaction_id}")
async def get_transaction_status(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
):
    """التحقق من حالة معاملة محددة"""
    from infrastructure.database.models import Transaction
    tx = await db.get(Transaction, transaction_id)
    if not tx:
        raise HTTPException(status_code=404, detail="المعاملة غير موجودة")
    return {
        "transaction_id": tx.transaction_id,
        "status": tx.status,
        "amount_egp": float(tx.amount_egp),
        "payment_method": tx.payment_method,
        "created_at": tx.created_at.isoformat(),
        "completed_at": (
            tx.completed_at.isoformat() if tx.completed_at else None
        ),
    }


# ============================================================
# api/routers/investors.py
# ============================================================

investors_router = APIRouter(
    prefix="/api/v1/investors", tags=["Investors"]
)


@investors_router.get("/wallet")
async def get_wallet(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """عرض محفظة المستثمر (الأراضي المملوكة، الرصيد، العمليات)"""
    user_id = request.state.user_id
    return await investor_svc.get_wallet(db, user_id)


@investors_router.get("/investment-history")
async def get_investment_history(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """سجل الاستثمار الكامل مع ترقيم الصفحات"""
    user_id = request.state.user_id
    return await investor_svc.get_investment_history(
        db, user_id, page, per_page
    )


# ============================================================
# api/routers/landowners.py
# ============================================================

landowners_router = APIRouter(
    prefix="/api/v1/landowners", tags=["Landowners"]
)


class UpdateLandStatus(BaseModel):
    status: Literal["Available", "Sold", "Reserved"]


class UpdateCommission(BaseModel):
    broker_commission_pct: float = Field(
        ge=0, le=10, description="نسبة عمولة السمسار (0-10%)"
    )
    platform_commission_pct: float = Field(
        ge=0, le=5, description="نسبة عمولة المنصة (0-5%)"
    )


@landowners_router.get("/lands")
async def get_owned_lands(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """عرض جميع الأراضي المملوكة مع ملخص مالي"""
    user_id = request.state.user_id
    return await landowner_svc.get_owned_lands(db, user_id)


@landowners_router.patch("/lands/{land_id}/status")
async def update_land_status(
    land_id: str,
    body: UpdateLandStatus,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """تحديث حالة بيع الأرض (Available/Sold/Reserved)"""
    user_id = request.state.user_id
    try:
        return await landowner_svc.update_land_status(
            db, user_id, land_id, body.status
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="غير مصرح")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@landowners_router.put("/lands/{land_id}/commission")
async def update_commission(
    land_id: str,
    body: UpdateCommission,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """تحديد نسبة عمولة السمسار والمنصة لكل أرض"""
    user_id = request.state.user_id
    try:
        return await landowner_svc.update_commission_settings(
            db, user_id, land_id,
            body.broker_commission_pct,
            body.platform_commission_pct,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="غير مصرح")


@landowners_router.get("/sales-report")
async def sales_report(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """تقرير المبيعات: الإجمالي، العمولات، الضرائب، صافي الإيرادات"""
    user_id = request.state.user_id
    return await landowner_svc.get_sales_report(db, user_id)


# ============================================================
# api/routers/incentives.py (مدمج مع investors)
# ============================================================

incentives_router = APIRouter(
    prefix="/api/v1/incentives", tags=["Incentives"]
)


@incentives_router.get("/calculate")
async def get_incentive_preview(
    request: Request,
    amount: float = Query(..., gt=0, description="مبلغ الشراء بالجنيه"),
    db: AsyncSession = Depends(get_db),
):
    """عرض الخصومات المتاحة قبل الشراء"""
    user_id = request.state.user_id
    return await incentive_svc.calculate_incentive(db, user_id, amount)


@incentives_router.post("/redeem-points")
async def redeem_loyalty_points(
    request: Request,
    points: int = Query(..., ge=100, description="عدد النقاط المراد استبدالها"),
    db: AsyncSession = Depends(get_db),
):
    """استبدال نقاط الولاء بخصم مالي (100 نقطة = 500 جنيه)"""
    user_id = request.state.user_id
    try:
        return await incentive_svc.redeem_loyalty_points(db, user_id, points)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))