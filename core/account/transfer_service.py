"""
خدمة نقل الملكية — transfer_ownership()
==========================================
نقل ملكية ذري (9 خطوات داخل معاملة واحدة).

هذا الملف يحتوي على:
    - InvestorStore: الفئة المُركَّبة من ثلاثة Mix-ins
    - transfer_ownership(): دالة نقل ملكية الأرض عند اكتمال الشراء

التزامن: يُدار عبر PostgreSQL row-level locks (SELECT ... FOR UPDATE).
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.account.investor_repository import InvestorCrudMixin
from core.account.landowner_repository import LandownerStore
from core.account.models import Investor
from core.account.transaction_repository import TransactionMixin
from core.account.wallet_service import WalletOperationsMixin

logger = logging.getLogger(__name__)

PLATFORM_COMMISSION_PCT = float(os.getenv("PLATFORM_COMMISSION_PCT", "0.5"))
# عمولة المنصة 0.5% من كل معاملة


class InvestorStore(InvestorCrudMixin, WalletOperationsMixin, TransactionMixin):
    """InvestorStore المُركَّب — يُستخدم داخل transfer_ownership فقط."""


async def transfer_ownership(
    land_id: str,
    buyer_id: str,
    session: AsyncSession,
    lands_catalog: Optional[Dict[str, Dict[str, Any]]] = None,
    commission_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """
    نقل ملكية أرض عند اكتمال عملية الشراء — ذري داخل معاملة واحدة.

    الخطوات التسع تُنفذ داخل session واحدة:
        1. التحقق من وجود الأرض في الكتالوج وأنها متاحة للبيع
        2. التحقق من أن المشتري مستثمر مسجل برصيد كافٍ
        3. حساب سعر البيع وعمولة المالك وعمولة المنصة
        4. خصم السعر من محفظة المشتري (إلغاء تجميد + خصم)
        5. تحديث حالة الأرض إلى "مباع"
        6. تحديث إحصائيات المشتري (عدد الأراضي، إجمالي المنفق)
        7. تحديث إحصائيات البائع (إجمالي المبيعات، العمولات)
        8. إضافة نقاط ولاء للمشتري
        9. إيداع صافي البيع في محفظة البائع (لو هو مستثمر أيضاً)

    Args:
        land_id: معرّف الأرض المراد نقل ملكيتها
        buyer_id: معرّف المشتري (المستثمر)
        session: AsyncSession نشط
        lands_catalog: كتالوج الأراضي (dict)
        commission_pct: نسبة العمولة (اختياري)

    Returns:
        dict بنتيجة العملية

    Raises:
        ValueError: في حالات الخطأ مع رسائل عربية
    """
    inv_store = InvestorStore(session)
    lo_store = LandownerStore(session)

    # ─── الخطوة 1: التحقق من الأرض ───
    if lands_catalog is None:
        raise ValueError("كتالوج الأراضي غير متوفر — مرّره كمعامل")

    land = lands_catalog.get(land_id)
    if not land:
        raise ValueError(f"الأرض {land_id} غير موجودة في الكتالوج")

    if land.get("investment_status") != "متاح":
        raise ValueError(
            f"الأرض {land_id} غير متاحة للبيع "
            f"(الحالة: {land.get('investment_status', 'غير محددة')})"
        )

    seller_id = land.get("owner_id", "")
    if not seller_id:
        raise ValueError(f"الأرض {land_id} ليس لها مالك مسجل")

    sale_price = float(land.get("total_price_egp", 0))
    if sale_price <= 0:
        raise ValueError(f"سعر الأرض {land_id} غير صالح: {sale_price}")

    # ─── الخطوة 2: التحقق من المشتري (مع قفل الصف) ───
    buyer_stmt = (
        select(Investor)
        .where(Investor.user_id == buyer_id)
        .with_for_update()
    )
    buyer_result = await session.execute(buyer_stmt)
    buyer = buyer_result.scalar_one_or_none()
    if not buyer:
        raise ValueError(f"المشتري {buyer_id} ليس مستثمراً مسجلاً")

    available_balance = buyer.available_balance_egp
    if available_balance < sale_price:
        raise ValueError(
            f"رصيد المشتري غير كافٍ. المتاح: {available_balance:,.2f} ج.م، "
            f"المطلوب: {sale_price:,.2f} ج.م"
        )

    # ─── الخطوة 3: حساب العمولات ───
    seller_data = await lo_store.get(seller_id)
    if seller_data:
        actual_commission_pct = (
            commission_pct
            if commission_pct is not None
            else seller_data["default_commission_pct"]
        )
    else:
        actual_commission_pct = commission_pct if commission_pct is not None else 2.5

    commission_amount = sale_price * (actual_commission_pct / 100.0)
    platform_fee = sale_price * (PLATFORM_COMMISSION_PCT / 100.0)
    net_to_seller = sale_price - commission_amount - platform_fee

    # ─── الخطوة 4: خصم من محفظة المشتري ───
    # إلغاء التجميد أولاً (لو كان مجمداً)
    if buyer.frozen_balance_egp >= sale_price:
        buyer.frozen_balance_egp -= sale_price
    else:
        # تجميد جزئي: نفك كل المجمد ونخصم من الرصيد
        unfrozen = buyer.frozen_balance_egp
        buyer.frozen_balance_egp = 0.0
        buyer.wallet_balance_egp -= (sale_price - unfrozen)

    buyer.updated_at = datetime.now(timezone.utc)

    # تسجيل معاملة الشراء
    await inv_store._add_transaction(
        user_id=buyer_id,
        tx_type="purchase",
        amount=-sale_price,
        description=f"شراء أرض {land_id} — {land.get('name', '')}",
        reference_id=f"sale-{land_id}",
    )
    logger.info(f"خصم {sale_price:,.2f} ج.م من محفظة المشتري {buyer_id}")

    # ─── الخطوة 5: تحديث حالة الأرض في الكتالوج (ذاكرة) ───
    land["investment_status"] = "مباع"
    land["sold_at"] = datetime.now(timezone.utc).isoformat()
    land["buyer_id"] = buyer_id
    land["sale_price_egp"] = sale_price
    land["commission_pct"] = actual_commission_pct

    # ─── الخطوة 6: تحديث إحصائيات المشتري ───
    await inv_store.increment_purchased(buyer_id, sale_price)

    # ─── الخطوة 7: تحديث إحصائيات البائع + نقل الملكية في DB ───
    if seller_data:
        await lo_store.record_sale(seller_id, sale_price, actual_commission_pct)
        await lo_store.transfer_land_ownership(seller_id, land_id, buyer_id)

    # ─── الخطوة 8: نقاط الولاء ───
    loyalty_earned = await inv_store.add_loyalty_points(buyer_id, sale_price)

    # ─── الخطوة 9: إيداع صافي البيع في محفظة البائع (لو هو مستثمر أيضاً) ───
    seller_is_investor = await inv_store.exists(seller_id)
    if seller_is_investor:
        try:
            await inv_store.deposit(
                seller_id,
                amount=net_to_seller,
                description=f"صافي بيع أرض {land_id} (بعد عمولة {actual_commission_pct}% + رسوم منصة)",
                reference_id=f"sale-{land_id}",
            )
        except Exception as e:
            logger.warning(f"فشل إيداع صافي البيع للمستثمر-البائع {seller_id}: {e}")

    # ─── بناء النتيجة ───
    transaction_id = f"tx-own-{uuid.uuid4().hex[:12]}"
    transferred_at = datetime.now(timezone.utc).isoformat()

    result = {
        "success": True,
        "land_id": land_id,
        "seller_id": seller_id,
        "buyer_id": buyer_id,
        "sale_price_egp": sale_price,
        "commission_egp": round(commission_amount, 2),
        "platform_fee_egp": round(platform_fee, 2),
        "net_to_seller_egp": round(net_to_seller, 2),
        "loyalty_points_earned": loyalty_earned,
        "new_owner_id": buyer_id,
        "transaction_id": transaction_id,
        "transferred_at": transferred_at,
        "message_ar": f"تم نقل ملكية الأرض {land_id} من {seller_id} إلى {buyer_id} بنجاح",
    }

    logger.info(
        f"نقل ملكية ناجح: {land_id} | البائع: {seller_id} | المشتري: {buyer_id} | "
        f"السعر: {sale_price:,.2f} ج.م | العمولة: {commission_amount:,.2f} ج.م | "
        f"نقاط الولاء: {loyalty_earned}"
    )

    return result
