"""
Smart Land Management Copilot V4.0
حساب المستثمر + حساب صاحب الأرض + نظام الحوافز — FastAPI Routers
"""

# ============================================================
# core/investor/service.py — خدمة المستثمر
# ============================================================

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.account.models import (
    InvestmentHistory,
    Investor,
    Land,
    LandCommissionSettings,
    Landowner,
    LoyaltyPointsLog,
    Transaction,
)


async def get_or_create_investor(
    db: AsyncSession, user_id: str
) -> Investor:
    """الحصول على حساب المستثمر أو إنشائه"""
    investor = await db.get(Investor, user_id)
    if not investor:
        investor = Investor(user_id=user_id)
        db.add(investor)
        await db.commit()
        await db.refresh(investor)
    return investor


async def get_wallet(
    db: AsyncSession, user_id: str
) -> dict:
    """عرض محفظة المستثمر الشاملة"""
    investor = await get_or_create_investor(db, user_id)

    # الأراضي المملوكة
    lands_result = await db.execute(
        select(Land).where(Land.current_owner_id == user_id)
    )
    owned_lands = lands_result.scalars().all()

    # المعاملات الأخيرة
    tx_result = await db.execute(
        select(Transaction)
        .where(Transaction.buyer_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(20)
    )
    recent_tx = tx_result.scalars().all()

    # حالة الخصم
    has_repeat_discount = (
        investor.total_lands_purchased >= REPEAT_BUYER_THRESHOLD
    )

    return {
        "wallet_balance_egp": float(investor.wallet_balance_egp),
        "total_lands_purchased": investor.total_lands_purchased,
        "total_invested_egp": float(investor.total_invested_egp),
        "loyalty_points": investor.loyalty_points,
        "discount_rate_pct": float(investor.discount_rate_pct),
        "has_repeat_buyer_discount": has_repeat_discount,
        "owned_lands_count": len(owned_lands),
        "owned_lands": owned_lands,
        "recent_transactions": recent_tx,
    }


async def get_investment_history(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """سجل الاستثمار مع ترقيم الصفحات"""
    offset = (page - 1) * per_page

    # إجمالي السجلات
    count_result = await db.execute(
        select(InvestmentHistory)
        .where(InvestmentHistory.user_id == user_id)
    )
    total = len(list(count_result.scalars().all()))

    # بيانات الصفحة
    result = await db.execute(
        select(InvestmentHistory)
        .where(InvestmentHistory.user_id == user_id)
        .order_by(InvestmentHistory.purchased_at.desc())
        .offset(offset)
        .limit(per_page)
    )

    return {
        "page": page,
        "per_page": per_page,
        "total_records": total,
        "total_pages": (total + per_page - 1) // per_page,
        "data": list(result.scalars().all()),
    }


async def record_purchase(
    db: AsyncSession,
    user_id: str,
    land_id: str,
    transaction_id: str,
    purchase_price: float,
    discount_applied: float,
) -> None:
    """تسجيل عملية شراء جديدة وتحديث بيانات المستثمر"""
    investor = await get_or_create_investor(db, user_id)

    # حساب نقاط الولاء (1 نقطة لكل 10,000 جنيه)
    earned_points = int(purchase_price // 10_000)

    # تحديث بيانات المستثمر
    investor.total_lands_purchased += 1
    investor.total_invested_egp += purchase_price
    investor.loyalty_points += earned_points

    # تفعيل خصم الشراء المتكرر
    if investor.total_lands_purchased >= REPEAT_BUYER_THRESHOLD:
        investor.discount_rate_pct = 5.0

    # إنشاء سجل الاستثمار
    history = InvestmentHistory(
        user_id=user_id,
        land_id=land_id,
        transaction_id=transaction_id,
        purchase_price=purchase_price,
        points_earned=earned_points,
        discount_applied=discount_applied,
    )
    db.add(history)
    await db.commit()


# ============================================================
# core/landowner/service.py — خدمة صاحب الأرض
# ============================================================


async def get_or_create_landowner(
    db: AsyncSession, user_id: str
) -> Landowner:
    """الحصول على حساب صاحب الأرض أو إنشائه"""
    owner = await db.get(Landowner, user_id)
    if not owner:
        owner = Landowner(user_id=user_id)
        db.add(owner)
        await db.commit()
        await db.refresh(owner)
    return owner


async def get_owned_lands(
    db: AsyncSession, owner_id: str
) -> dict:
    """عرض جميع الأراضي المملوكة مع ملخص مالي"""
    owner = await get_or_create_landowner(db, owner_id)

    result = await db.execute(
        select(Land)
        .where(Land.owner_id == owner_id)
        .order_by(Land.created_at.desc())
    )
    lands = result.scalars().all()

    return {
        "total_listed": owner.total_lands_listed,
        "total_sold": owner.total_lands_sold,
        "total_sales_egp": float(owner.total_sales_egp),
        "default_broker_commission_pct": float(
            owner.default_broker_commission_pct
        ),
        "lands": lands,
    }


async def update_land_status(
    db: AsyncSession,
    owner_id: str,
    land_id: str,
    new_status: str,
) -> dict:
    """تحديث حالة بيع الأرض"""
    land = await db.get(Land, land_id)
    if not land or land.owner_id != owner_id:
        raise PermissionError("غير مصرح بتحديث هذه الأرض")

    valid_statuses = {"Available", "Sold", "Reserved"}
    if new_status not in valid_statuses:
        raise ValueError(f"الحالة غير صالحة: {new_status}")

    old_status = land.status
    land.status = new_status

    owner = await get_or_create_landowner(db, owner_id)
    if new_status == "Sold" and old_status != "Sold":
        owner.total_lands_sold += 1

    await db.commit()
    return {
        "status": "updated",
        "land_id": land_id,
        "old_status": old_status,
        "new_status": new_status,
    }


async def update_commission_settings(
    db: AsyncSession,
    owner_id: str,
    land_id: str,
    broker_pct: float,
    platform_pct: float,
) -> dict:
    """تحديث إعدادات العمولة لأرض محددة"""
    # التحقق من ملكية الأرض
    land = await db.get(Land, land_id)
    if not land or land.owner_id != owner_id:
        raise PermissionError("غير مصرح")

    # البحث عن إعدادات موجودة أو إنشاء جديدة
    result = await db.execute(
        select(LandCommissionSettings).where(
            LandCommissionSettings.land_id == land_id
        )
    )
    settings = result.scalar_one_or_none()

    if settings:
        settings.broker_commission_pct = broker_pct
        settings.platform_commission_pct = platform_pct
        settings.updated_at = datetime.now(timezone.utc)
    else:
        settings = LandCommissionSettings(
            land_id=land_id,
            owner_id=owner_id,
            broker_commission_pct=broker_pct,
            platform_commission_pct=platform_pct,
        )
        db.add(settings)

    await db.commit()
    return {
        "status": "updated",
        "land_id": land_id,
        "broker_commission_pct": float(broker_pct),
        "platform_commission_pct": float(platform_pct),
    }


async def get_sales_report(
    db: AsyncSession, owner_id: str
) -> dict:
    """تقرير المبيعات والإيرادات"""
    result = await db.execute(
        select(Transaction).where(
            Transaction.seller_id == owner_id,
            Transaction.status == "Completed",
        )
    )
    txs = list(result.scalars().all())

    total_sales = sum(t.amount_egp for t in txs)
    total_fees = sum(t.platform_fee_egp for t in txs)
    total_taxes = sum(t.tax_amount_egp for t in txs)

    return {
        "total_sales_egp": float(total_sales),
        "platform_fees_egp": float(total_fees),
        "taxes_egp": float(total_taxes),
        "net_income_egp": float(total_sales - total_fees - total_taxes),
        "transactions_count": len(txs),
        "transactions": txs,
    }


# ============================================================
# core/incentive/service.py — خدمة الحوافز
# ============================================================

REPEAT_BUYER_THRESHOLD = 3       # عدد المشتريات لتفعيل الخصم
REPEAT_BUYER_DISCOUNT = 5.0     # نسبة الخصم %
POINTS_PER_10K_EGP = 1          # نقطة لكل 10,000 جنيه
POINTS_REDEMPTION_RATE = 500.0  # 100 نقطة = 500 جنيه
MAX_TOTAL_DISCOUNT_PCT = 10.0   # الحد الأقصى للخصم الكلي


async def calculate_incentive(
    db: AsyncSession, user_id: str, amount: float
) -> dict:
    """حساب الخصومات ونقاط الولاء المتاحة"""
    investor = await db.get(Investor, user_id)
    if not investor:
        investor = Investor(user_id=user_id)
        db.add(investor)
        await db.commit()

    # 1. خصم الشراء المتكرر
    repeat_discount = 0.0
    if investor.total_lands_purchased >= REPEAT_BUYER_THRESHOLD:
        repeat_discount = round(amount * (REPEAT_BUYER_DISCOUNT / 100), 2)

    # 2. خصم نقاط الولاء (اختياري - حساب أقصى ممكن)
    points_value = 0.0
    if investor.loyalty_points >= 100:
        redeem_points = (investor.loyalty_points // 100) * 100
        points_value = round((redeem_points / 100) * POINTS_REDEMPTION_RATE, 2)

    # 3. التحقق من الحد الأقصى للخصم
    total_discount = repeat_discount + points_value
    max_discount = amount * (MAX_TOTAL_DISCOUNT_PCT / 100)
    if total_discount > max_discount and total_discount > 0:
        ratio = max_discount / total_discount
        repeat_discount = round(repeat_discount * ratio, 2)
        points_value = round(points_value * ratio, 2)

    # 4. حساب نقاط الولاء المكتسبة
    earned_points = int(amount // 10_000)

    return {
        "repeat_discount_egp": repeat_discount,
        "loyalty_discount_egp": points_value,
        "total_discount_egp": round(repeat_discount + points_value, 2),
        "points_to_earn": earned_points,
        "final_price_egp": round(amount - repeat_discount - points_value, 2),
        "is_repeat_buyer": investor.total_lands_purchased >= REPEAT_BUYER_THRESHOLD,
        "available_loyalty_points": investor.loyalty_points,
    }


async def redeem_loyalty_points(
    db: AsyncSession,
    user_id: str,
    points: int,
) -> dict:
    """استبدال نقاط الولاء بخصم مالي"""
    if points < 100 or points % 100 != 0:
        raise ValueError("الحد الأدنى للاستبدال 100 نقطة (بمضاعفات 100)")

    investor = await db.get(Investor, user_id)
    if not investor or investor.loyalty_points < points:
        raise ValueError("رصيد النقاط غير كافٍ")

    discount = (points / 100) * POINTS_REDEMPTION_RATE
    investor.loyalty_points -= points

    log = LoyaltyPointsLog(
        user_id=user_id,
        points_used=points,
        reason=f"استبدال {points} نقطة = {discount:.2f} جنيه",
    )
    db.add(log)
    await db.commit()

    return {
        "discount_egp": float(discount),
        "points_redeemed": points,
        "remaining_points": investor.loyalty_points,
    }