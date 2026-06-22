"""
مسارات المستثمرين — InvestorRouter
=====================================
POST   /investors                    → إنشاء حساب
GET    /investors                    → قائمة المستثمرين
GET    /investors/{id}               → بيانات مستثمر
GET    /investors/{id}/wallet        → المحفظة
GET    /investors/{id}/transactions  → سجل المعاملات
POST   /investors/{id}/deposit       → إيداع
POST   /investors/{id}/withdraw      → سحب
POST   /investors/{id}/redeem-loyalty → استبدال ولاء
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.routes._deps import get_investor_store
from core.domain.entities import (
    APIResponse,
    InvestorCreateRequest,
    LoyaltyRedeemRequest,
    WalletDepositRequest,
)

router = APIRouter(prefix="/api/v1", tags=["investors"])


@router.post("/investors", response_model=APIResponse, status_code=201)
async def create_investor(req: InvestorCreateRequest):
    """
    إنشاء حساب مستثمر جديد.

    - **user_id**: معرّف المستخدم من خدمة المصادقة
    - **initial_deposit_egp**: الإيداع الأولي (اختياري)
    """
    store = get_investor_store()
    try:
        investor = store.create(
            user_id=req.user_id,
            initial_deposit=req.initial_deposit_egp,
        )
        return APIResponse(
            data=investor,
            message=f"تم إنشاء حساب المستثمر {req.user_id} بنجاح",
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/investors", response_model=APIResponse)
async def list_investors(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """قائمة جميع المستثمرين (ترقيم الصفحات)."""
    store = get_investor_store()
    all_investors = store.get_all()

    total = len(all_investors)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    page_data = all_investors[start : start + per_page]

    return APIResponse(
        data=page_data,
        meta={"total": total, "page": page, "per_page": per_page, "total_pages": total_pages},
        message=f"قائمة المستثمرين ({total} مستثمر)",
    )


@router.get("/investors/{user_id}", response_model=APIResponse)
async def get_investor(user_id: str):
    """استرجاع بيانات مستثمر واحد."""
    store = get_investor_store()
    investor = store.get(user_id)
    if not investor:
        raise HTTPException(status_code=404, detail=f"المستثمر {user_id} غير موجود")
    return APIResponse(data=investor, message="تم استرجاع بيانات المستثمر")


@router.get("/investors/{user_id}/wallet", response_model=APIResponse)
async def get_investor_wallet(user_id: str):
    """
    بيانات محفظة المستثمر.

    يُرجع: الرصيد الكلي، الرصيد المجمد، الرصيد المتاح،
           نقاط الولاء، عدد الأراضي المشتراة، إجمالي المنفق.
    """
    store = get_investor_store()
    wallet = store.get_wallet(user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail=f"المستثمر {user_id} غير موجود")

    return APIResponse(
        data=wallet,
        message="تم استرجاع بيانات المحفظة",
    )


@router.get("/investors/{user_id}/transactions", response_model=APIResponse)
async def get_investor_transactions(
    user_id: str,
    tx_type: Optional[str] = Query(None, description="فلتر: deposit / purchase / withdrawal / loyalty_earn / loyalty_redeem"),
    limit: int = Query(50, ge=1, le=200),
):
    """سجل معاملات محفظة المستثمر."""
    store = get_investor_store()

    if not store.exists(user_id):
        raise HTTPException(status_code=404, detail=f"المستثمر {user_id} غير موجود")

    txs = store.get_transactions(user_id, tx_type=tx_type, limit=limit)
    return APIResponse(
        data=txs,
        meta={"user_id": user_id, "count": len(txs), "type_filter": tx_type},
        message=f"سجل المعاملات ({len(txs)} معاملة)",
    )


@router.post("/investors/{user_id}/deposit", response_model=APIResponse)
async def deposit_to_wallet(user_id: str, req: WalletDepositRequest):
    """
    إيداع مبلغ في محفظة المستثمر.

    - **amount_egp**: مبلغ الإيداع (يجب أن يكون موجباً)
    - **description**: وصف العملية
    """
    store = get_investor_store()

    if not store.exists(user_id):
        raise HTTPException(status_code=404, detail=f"المستثمر {user_id} غير موجود")

    try:
        wallet = store.deposit(
            user_id=user_id,
            amount=req.amount_egp,
            description=req.description,
        )
        return APIResponse(
            data=wallet,
            message=f"تم إيداع {req.amount_egp:,.2f} ج.م بنجاح",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/investors/{user_id}/withdraw", response_model=APIResponse)
async def withdraw_from_wallet(user_id: str, req: WalletDepositRequest):
    """
    سحب مبلغ من محفظة المستثمر.

    - **amount_egp**: مبلغ السحب
    - **description**: وصف العملية
    """
    store = get_investor_store()

    if not store.exists(user_id):
        raise HTTPException(status_code=404, detail=f"المستثمر {user_id} غير موجود")

    try:
        wallet = store.withdraw(
            user_id=user_id,
            amount=req.amount_egp,
            description=req.description or "سحب من المحفظة",
        )
        return APIResponse(
            data=wallet,
            message=f"تم سحب {req.amount_egp:,.2f} ج.م بنجاح",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/investors/{user_id}/redeem-loyalty", response_model=APIResponse)
async def redeem_loyalty_points(user_id: str, req: LoyaltyRedeemRequest):
    """
    استبدال نقاط الولاء برصيد في المحفظة.

    - **points**: عدد النقاط المطلوب استبدالها
    - كل نقطة = 10 جنيه (قابل للتعديل)
    """
    store = get_investor_store()

    if not store.exists(user_id):
        raise HTTPException(status_code=404, detail=f"المستثمر {user_id} غير موجود")

    try:
        egp_amount = store.redeem_loyalty_points(user_id, req.points)
        wallet = store.get_wallet(user_id)
        return APIResponse(
            data={
                "points_redeemed": req.points,
                "egp_credited": egp_amount,
                "wallet": wallet,
            },
            message=f"تم استبدال {req.points} نقطة = {egp_amount:,.2f} ج.م",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
