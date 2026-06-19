"""
خدمة الوسطاء — BrokerService
==============================
منطق الأعمال لإدارة الوسطاء وتعيينهم وحساب العمولات.

يحتوي على:
    - register_broker: تسجيل وسيط جديد
    - update_broker_commission: تحديث نسبة العمولة
    - assign_broker_to_land: تعيين وسيط لأرض
    - complete_sale_and_pay_commission: إتمام بيع وحساب عمولة
    - get_broker_profile, get_broker_lands, get_broker_earnings
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from core.account.broker_repository import BrokerRepository
from core.domain.verification_service import LandVerificationService

logger = logging.getLogger(__name__)


class BrokerService:
    """خدمة منطق الأعمال للوسطاء."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = BrokerRepository(session)
        self.verification = LandVerificationService(session)

    # ──────────────────────────────────────────
    # تسجيل وسيط جديد
    # ──────────────────────────────────────────

    async def register_broker(
        self,
        user_id: str,
        full_name: str,
        phone_number: str = "",
        email: str = "",
        default_commission_rate: float = 2.5,
        specialization: Optional[List[str]] = None,
        bio: str = "",
    ) -> Dict[str, Any]:
        """تسجيل وسيط جديد في المنصة."""
        # التحقق من صحة النسبة
        if not (1.0 <= default_commission_rate <= 20.0):
            raise ValueError("نسبة العمولة يجب أن تكون بين 1% و 20%")

        # إنشاء السجل
        broker_data = await self.repo.create(
            user_id=user_id,
            full_name=full_name,
            phone_number=phone_number,
            email=email,
            specialization=specialization,
            bio=bio,
            default_commission_rate=default_commission_rate,
        )
        logger.info(f"تسجيل وسيط جديد: {full_name} (user_id: {user_id})")
        return broker_data

    # ──────────────────────────────────────────
    # استرجاع بيانات الوسيط
    # ──────────────────────────────────────────

    async def get_broker_profile(self, broker_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع ملف الوسيط الكامل مع إحصائياته."""
        broker = await self.repo.get(broker_id)
        if not broker:
            return None

        # جلب التعيينات النشطة
        assignments = await self.repo.get_assignments_by_broker(broker_id)
        active_assignments = [a for a in assignments if a["status"] == "active"]

        # جلب الأراضي المرتبطة
        lands = await self.repo.get_lands_by_broker(broker_id)

        # جلب الأرباح
        earnings = await self.repo.get_broker_earnings(broker_id)

        return {
            "broker": broker,
            "active_assignments_count": len(active_assignments),
            "total_assignments_count": len(assignments),
            "lands_managed_count": len(lands),
            "earnings": earnings,
        }

    async def list_broker_lands(self, broker_id: str) -> List[Dict[str, Any]]:
        """عرض الأراضي التي يديرها الوسيط."""
        return await self.repo.get_lands_by_broker(broker_id)

    # ──────────────────────────────────────────
    # تعيين وسيط لأرض
    # ──────────────────────────────────────────

    async def assign_broker_to_land(
        self,
        land_id: str,
        broker_id: str,
        commission_percent: Optional[float] = None,
        requesting_user_id: str = "",
    ) -> Dict[str, Any]:
        """
        تعيين وسيط لأرض معينة.

        Args:
            land_id: معرّف الأرض
            broker_id: معرّف الوسيط
            commission_percent: نسبة العمولة (اختياري، يستخدم الافتراضية)
            requesting_user_id: المستخدم الذي طلب التعيين (للتحقق من الصلاحيات)
        """
        # التحقق من صحة النسبة إن وُجدت
        if commission_percent is not None:
            if not (1.0 <= commission_percent <= 20.0):
                raise ValueError("نسبة العمولة يجب أن تكون بين 1% و 20%")
        # التحقق من صلاحية المستخدم (مالك الأرض أو مسؤول)
        from core.account.models import OwnedLand
        land_stmt = select(OwnedLand).where(OwnedLand.land_id == land_id)
        land_result = await self.session.execute(land_stmt)
        land = land_result.scalar_one_or_none()
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")
        if land.landowner_id != requesting_user_id:
            raise ValueError("فقط مالك الأرض يمكنه تعيين وسيط")

        # إنشاء التعيين
        assignment = await self.repo.assign_broker(
            land_id=land_id,
            broker_id=broker_id,
            commission_percent=commission_percent,
        )

        # تحديث حالة التحقق إذا كانت الأرض مُتحققة
        # (لا يتغير)

        logger.info(f"تعيين وسيط {broker_id} للأرض {land_id} بواسطة {requesting_user_id}")
        return assignment

    async def remove_broker_from_land(self, land_id: str, broker_id: str) -> bool:
        """إزالة وسيط من أرض."""
        return await self.repo.cancel_assignment(land_id, broker_id)

    # ──────────────────────────────────────────
    # حساب ودفع العمولات
    # ──────────────────────────────────────────

    async def process_sale_commission(
        self,
        land_id: str,
        sale_amount_egp: float,
        transaction_id: str,
    ) -> Dict[str, Any]:
        """
        معالجة عمولة الوسيط عند بيع أرض.

        1. يجلب تعيين الوسيط النشط للأرض
        2. ينشئ سجل BrokerTransaction
        3. يحدّث إحصائيات الوسيط
        """
        assignment = await self.repo.get_active_assignment_by_land(land_id)
        if not assignment:
            # لا يوجد وسيط معين
            return {"broker_commission_egp": 0, "broker_id": None}

        broker_id = assignment["broker_id"]
        commission_rate = assignment["commission_percent"]

        # إنشاء سجل المعاملة
        tx = await self.repo.add_transaction(
            broker_id=broker_id,
            transaction_id=transaction_id,
            land_id=land_id,
            sale_amount_egp=sale_amount_egp,
            commission_rate_pct=commission_rate,
        )

        # تحديث إحصائيات الوسيط
        net_commission = sale_amount_egp * (commission_rate / 100.0)
        await self.repo.increment_deals(broker_id, net_commission)

        # إنهاء التعيين
        await self.repo.complete_assignment(land_id, broker_id)

        logger.info(
            f"عمولة بيع للأرض {land_id}: وسيط={broker_id}, "
            f"مبلغ={sale_amount_egp:,.2f} ج.م, عمولة={net_commission:,.2f} ج.م"
        )
        return {
            "broker_id": broker_id,
            "broker_commission_egp": round(net_commission, 2),
            "transaction_id": tx["id"],
        }

    async def pay_broker_commission(self, transaction_id: str) -> Dict[str, Any]:
        """دفع عمولة معلقة لوسيط (بواسطة المسؤول)."""
        tx = await self.repo.mark_transaction_paid(transaction_id)
        broker_id = tx["broker_id"]
        # هنا يمكن إضافة منطق تحويل الأموال لمحفظة الوسيط
        # مؤقتاً فقط نسجّل الدفع
        logger.info(f"تم دفع عمولة الوسيط {broker_id}: {tx['net_commission_egp']} ج.م")
        return tx

    # ──────────────────────────────────────────
    # مجتمع الوسطاء (للباحثين)
    # ──────────────────────────────────────────

    async def list_broker_community(
        self,
        query: str = "",
        specialization: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """عرض قائمة الوسطاء النشطين مع البحث."""
        return await self.repo.search(query=query, specialization=specialization, limit=limit)

    async def get_broker_stats(self) -> Dict[str, Any]:
        """إحصائيات عامة عن مجتمع الوسطاء."""
        all_brokers = await self.repo.get_all(limit=1000)
        active = [b for b in all_brokers if b["status"] == "active"]
        return {
            "total_brokers": len(all_brokers),
            "active_brokers": len(active),
            "avg_commission_rate": round(
                sum(b["default_commission_rate"] for b in active) / max(len(active), 1), 2
            ),
            "top_brokers": sorted(
                active, key=lambda b: b["total_deals_closed"], reverse=True
            )[:10],
        }