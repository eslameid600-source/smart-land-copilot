"""
مخزن الوسطاء — BrokerRepository
==================================
CRUD كامل لعمليات الوسطاء وعمولاتهم وتعييناتهم.

يحتوي على:
    - تسجيل وسيط جديد / استرجاع / تحديث / حذف
    - إدارة التعيينات (تعيين / تفعيل / إنهاء)
    - إدارة معاملات العمولات
    - البحث في قائمة الوسطاء النشطين
"""

import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.account.models import (
    Broker,
    BrokerAssignment,
    BrokerTransaction,
    BrokerStatus,
    BrokerAssignmentStatus,
    BrokerTransactionStatus,
)

logger = logging.getLogger(__name__)


def _generate_broker_code(length: int = 8) -> str:
    """توليد كود فريد للوسيط من أحرف عشوائية."""
    alphabet = string.ascii_uppercase + string.digits
    return "BRK-" + "".join(secrets.choice(alphabet) for _ in range(length))


class BrokerRepository:
    """مخزن الوسطاء — يعمل مباشرة مع PostgreSQL عبر AsyncSession."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ──────────────────────────────────────────
    # Broker CRUD
    # ──────────────────────────────────────────

    async def create(
        self,
        user_id: str,
        full_name: str,
        phone_number: str = "",
        email: str = "",
        company_name: str = "",
        license_number: str = "",
        bio: str = "",
        specialization: Optional[List[str]] = None,
        default_commission_rate: float = 2.5,
    ) -> Dict[str, Any]:
        """
        تسجيل وسيط جديد.

        Args:
            user_id: معرّف المستخدم (يجب أن يكون role = CERTIFIED_BROKER)
            full_name: اسم الوسيط الكامل
            phone_number: رقم الهاتف
            email: البريد الإلكتروني
            company_name: اسم الشركة (إن وُجدت)
            license_number: رقم الرخصة
            bio: نبذة عن الوسيط
            specialization:	list specialized in (e.g., ["سكني", "تجاري"])
            default_commission_rate: نسبة العمولة الافتراضية (1% إلى 20%)
        """
        if not (1.0 <= default_commission_rate <= 20.0):
            raise ValueError("نسبة العمولة يجب أن تكون بين 1% و 20%")

        # التحقق من عدم التكرار
        existing = await self.get_by_user_id(user_id)
        if existing:
            raise ValueError(f"المستخدم {user_id} مسجل كوسيط مسبقاً")

        # توليد كود فريد
        broker_code = _generate_broker_code()
        # التأكد من تفرد الكود
        while await self.get_by_broker_code(broker_code):
            broker_code = _generate_broker_code()

        broker = Broker(
            user_id=user_id,
            full_name=full_name,
            phone_number=phone_number or None,
            email=email or None,
            company_name=company_name or None,
            license_number=license_number or None,
            bio=bio or None,
            specialization=specialization or [],
            default_commission_rate=float(default_commission_rate),
            broker_code=broker_code,
            status=BrokerStatus.INACTIVE,
        )
        self.session.add(broker)
        await self.session.flush()
        await self.session.refresh(broker)

        logger.info(f"تسجيل وسيط جديد: {full_name} (كود: {broker_code})")
        return broker.to_dict()

    async def get(self, broker_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع بيانات وسيط بالمعرف."""
        stmt = select(Broker).where(Broker.id == broker_id)
        result = await self.session.execute(stmt)
        broker = result.scalar_one_or_none()
        return broker.to_dict() if broker else None

    async def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع بيانات وسيط بمعرّف المستخدم."""
        stmt = select(Broker).where(Broker.user_id == user_id)
        result = await self.session.execute(stmt)
        broker = result.scalar_one_or_none()
        return broker.to_dict() if broker else None

    async def get_by_broker_code(self, broker_code: str) -> Optional[Dict[str, Any]]:
        """استرجاع وسيط بالكود."""
        stmt = select(Broker).where(Broker.broker_code == broker_code)
        result = await self.session.execute(stmt)
        broker = result.scalar_one_or_none()
        return broker.to_dict() if broker else None

    async def get_all(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """استرجاع جميع الوسطاء مع فلتر اختياري للحالة."""
        stmt = select(Broker).order_by(Broker.created_at.desc())
        if status:
            stmt = stmt.where(Broker.status == status)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return [b.to_dict() for b in result.scalars().all()]

    async def get_active_brokers(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """استرجاع الوسطاء النشطين فقط."""
        stmt = (
            select(Broker)
            .where(Broker.status == BrokerStatus.ACTIVE)
            .where(Broker.verified_by_admin == True)
            .order_by(Broker.rating_avg.desc().nullslast(), Broker.total_deals_closed.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [b.to_dict() for b in result.scalars().all()]

    async def search(
        self,
        query: str = "",
        specialization: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """البحث عن وسطاء بالاسم أو الكود أو التخصص."""
        stmt = select(Broker).where(Broker.status == BrokerStatus.ACTIVE)
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Broker.full_name.ilike(pattern),
                    Broker.broker_code.ilike(pattern),
                    Broker.company_name.ilike(pattern),
                )
            )
        if specialization:
            # البحث داخل مصفوفة JSON
            stmt = stmt.where(Broker.specialization.contains([specialization]))
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return [b.to_dict() for b in result.scalars().all()]

    async def update_status(self, broker_id: str, new_status: str) -> Dict[str, Any]:
        """تحديث حالة الوسيط."""
        if new_status not in [s.value for s in BrokerStatus]:
            raise ValueError(f"حالة غير صالحة: {new_status}")

        stmt = (
            select(Broker).where(Broker.id == broker_id).with_for_update()
        )
        result = await self.session.execute(stmt)
        broker = result.scalar_one_or_none()
        if not broker:
            raise ValueError(f"الوسيط {broker_id} غير موجود")

        broker.status = BrokerStatus(new_status)
        broker.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(broker)
        return broker.to_dict()

    async def update_commission_rate(self, broker_id: str, new_rate: float) -> Dict[str, Any]:
        """تحديث نسبة العمولة الافتراضية للوسيط."""
        if not (1.0 <= new_rate <= 20.0):
            raise ValueError("نسبة العمولة يجب أن تكون بين 1% و 20%")

        stmt = (
            select(Broker).where(Broker.id == broker_id).with_for_update()
        )
        result = await self.session.execute(stmt)
        broker = result.scalar_one_or_none()
        if not broker:
            raise ValueError(f"الوسيط {broker_id} غير موجود")

        old_rate = broker.default_commission_rate
        broker.default_commission_rate = float(new_rate)
        broker.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        logger.info(f"تحديث عمولة الوسيط {broker_id}: {old_rate}% → {new_rate}%")
        await self.session.refresh(broker)
        return broker.to_dict()

    async def increment_deals(self, broker_id: str, commission_earned: float) -> Dict[str, Any]:
        """زيادة عدد الصفقات المغلقة وإجمالي العمولات بعد إتمام البيع."""
        stmt = (
            select(Broker).where(Broker.id == broker_id).with_for_update()
        )
        result = await self.session.execute(stmt)
        broker = result.scalar_one_or_none()
        if not broker:
            raise ValueError(f"الوسيط {broker_id} غير موجود")

        broker.total_deals_closed += 1
        broker.total_commission_earned_egp += float(commission_earned)
        broker.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(broker)
        return broker.to_dict()

    async def delete(self, broker_id: str) -> bool:
        """حذف وسيط (ليس منطقياً عادة، لكنه متاح)."""
        stmt = delete(Broker).where(Broker.id == broker_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    # ──────────────────────────────────────────
    # Broker Assignments
    # ──────────────────────────────────────────

    async def assign_broker(
        self,
        land_id: str,
        broker_id: str,
        commission_percent: Optional[float] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        تعيين وسيط لأرض معينة.

        Args:
            land_id: معرّف الأرض
            broker_id: معرّف الوسيط
            commission_percent: نسبة العمولة لهذه الأرض (اختياري)
            notes: ملاحظات
        """
        # التحقق من وجود الوسيط
        broker = await self.get(broker_id)
        if not broker:
            raise ValueError(f"الوسيط {broker_id} غير موجود")
        if broker["status"] != BrokerStatus.ACTIVE.value:
            raise ValueError(f"الوسيط {broker_id} غير نشط")
        if not broker["verified_by_admin"]:
            raise ValueError(f"الوسيط {broker_id} لم يتم التحقق منه بواسطة الإدارة")

        # استخدام نسبة الوسيط الافتراضية إن لم تُحدد
        if commission_percent is None:
            commission_percent = float(broker["default_commission_rate"])
        else:
            if not (1.0 <= commission_percent <= 20.0):
                raise ValueError("نسبة العمولة يجب أن تكون بين 1% و 20%")

        # التحقق من عدم وجود تعيين نشط لنفس الأرض
        existing = await self.get_active_assignment_by_land(land_id)
        if existing:
            raise ValueError(
                f"الأرض {land_id} لها تعيين نشط مسبقاً (وسيط: {existing['broker_id']})"
            )

        assignment = BrokerAssignment(
            land_id=land_id,
            broker_id=broker_id,
            commission_percent=float(commission_percent),
            status=BrokerAssignmentStatus.ACTIVE,
            notes=notes or None,
        )
        self.session.add(assignment)
        await self.session.flush()
        await self.session.refresh(assignment)

        # تحديث حقل broker_id في OwnedLand
        from core.account.models import OwnedLand
        update_land = (
            update(OwnedLand)
            .where(OwnedLand.land_id == land_id)
            .values(broker_id=broker_id, commission_percent=float(commission_percent))
        )
        await self.session.execute(update_land)

        logger.info(f"تعيين وسيط {broker_id} للأرض {land_id} (عمولة: {commission_percent}%)")
        return assignment.to_dict()

    async def get_assignment_by_land(self, land_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع تعيين الوسيط لأرض معينة."""
        stmt = (
            select(BrokerAssignment)
            .where(BrokerAssignment.land_id == land_id)
            .order_by(BrokerAssignment.assigned_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        assignment = result.scalar_one_or_none()
        return assignment.to_dict() if assignment else None

    async def get_active_assignment_by_land(self, land_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع التعيين النشط لأرض."""
        stmt = (
            select(BrokerAssignment)
            .where(
                and_(
                    BrokerAssignment.land_id == land_id,
                    BrokerAssignment.status == BrokerAssignmentStatus.ACTIVE,
                )
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        assignment = result.scalar_one_or_none()
        return assignment.to_dict() if assignment else None

    async def cancel_assignment(self, land_id: str, broker_id: str) -> bool:
        """إلغاء تعيين وسيط من أرض."""
        stmt = (
            select(BrokerAssignment)
            .where(
                and_(
                    BrokerAssignment.land_id == land_id,
                    BrokerAssignment.broker_id == broker_id,
                    BrokerAssignment.status == BrokerAssignmentStatus.ACTIVE,
                )
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        assignment = result.scalar_one_or_none()
        if not assignment:
            return False

        assignment.status = BrokerAssignmentStatus.CANCELLED
        assignment.cancelled_at = datetime.now(timezone.utc)
        await self.session.flush()

        # إزالة الوسيط من OwnedLand
        from core.account.models import OwnedLand
        update_land = (
            update(OwnedLand)
            .where(OwnedLand.land_id == land_id)
            .values(broker_id=None, commission_percent=None)
        )
        await self.session.execute(update_land)

        logger.info(f"إلغاء تعيين الوسيط {broker_id} من الأرض {land_id}")
        return True

    async def complete_assignment(self, land_id: str, broker_id: str) -> bool:
        """إنهاء التعيين بعد إتمام البيع."""
        stmt = (
            select(BrokerAssignment)
            .where(
                and_(
                    BrokerAssignment.land_id == land_id,
                    BrokerAssignment.broker_id == broker_id,
                    BrokerAssignment.status == BrokerAssignmentStatus.ACTIVE,
                )
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        assignment = result.scalar_one_or_none()
        if not assignment:
            return False

        assignment.status = BrokerAssignmentStatus.COMPLETED
        assignment.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        logger.info(f"إتمام تعيين الوسيط {broker_id} للأرض {land_id}")
        return True

    async def get_assignments_by_broker(self, broker_id: str) -> List[Dict[str, Any]]:
        """استرجاع جميع تعيينات وسيط معين."""
        stmt = (
            select(BrokerAssignment)
            .where(BrokerAssignment.broker_id == broker_id)
            .order_by(BrokerAssignment.assigned_at.desc())
        )
        result = await self.session.execute(stmt)
        return [a.to_dict() for a in result.scalars().all()]

    # ──────────────────────────────────────────
    # Broker Transactions (العمولات)
    # ──────────────────────────────────────────

    async def add_transaction(
        self,
        broker_id: str,
        transaction_id: str,
        land_id: str,
        sale_amount_egp: float,
        commission_rate_pct: float,
        platform_fee_egp: float = 0.0,
        notes: str = "",
    ) -> Dict[str, Any]:
        """إنشاء سجل عمولة جديد."""
        commission_amount = sale_amount_egp * (commission_rate_pct / 100.0)
        net_commission = commission_amount - platform_fee_egp

        tx = BrokerTransaction(
            broker_id=broker_id,
            transaction_id=transaction_id,
            land_id=land_id,
            sale_amount_egp=float(sale_amount_egp),
            commission_rate_pct=float(commission_rate_pct),
            commission_amount_egp=float(commission_amount),
            platform_fee_egp=float(platform_fee_egp),
            net_commission_egp=float(net_commission),
            status=BrokerTransactionStatus.PENDING,
            notes=notes or None,
        )
        self.session.add(tx)
        await self.session.flush()
        await self.session.refresh(tx)
        return tx.to_dict()

    async def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع معاملة عمولة."""
        stmt = select(BrokerTransaction).where(BrokerTransaction.id == tx_id)
        result = await self.session.execute(stmt)
        tx = result.scalar_one_or_none()
        return tx.to_dict() if tx else None

    async def get_broker_earnings(self, broker_id: str) -> Dict[str, Any]:
        """حساب إجمالي أرباح الوسيط."""
        stmt = select(BrokerTransaction).where(BrokerTransaction.broker_id == broker_id)
        result = await self.session.execute(stmt)
        txs = result.scalars().all()

        total_pending = sum(t.net_commission_egp for t in txs if t.status == BrokerTransactionStatus.PENDING)
        total_paid = sum(t.net_commission_egp for t in txs if t.status == BrokerTransactionStatus.PAID)
        total_cancelled = sum(t.net_commission_egp for t in txs if t.status == BrokerTransactionStatus.CANCELLED)

        return {
            "broker_id": broker_id,
            "total_pending_egp": round(float(total_pending), 2),
            "total_paid_egp": round(float(total_paid), 2),
            "total_cancelled_egp": round(float(total_cancelled), 2),
            "total_net_egp": round(float(total_pending + total_paid), 2),
            "transactions_count": len(txs),
        }

    async def mark_transaction_paid(self, tx_id: str) -> Dict[str, Any]:
        """تحديث حالة معاملة العمولة إلى مدفوعة."""
        stmt = (
            select(BrokerTransaction).where(BrokerTransaction.id == tx_id).with_for_update()
        )
        result = await self.session.execute(stmt)
        tx = result.scalar_one_or_none()
        if not tx:
            raise ValueError(f"المعاملة {tx_id} غير موجودة")
        tx.status = BrokerTransactionStatus.PAID
        tx.paid_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(tx)
        return tx.to_dict()

    async def get_broker_transactions(
        self,
        broker_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """استرجاع معاملات وسيط معين."""
        stmt = (
            select(BrokerTransaction)
            .where(BrokerTransaction.broker_id == broker_id)
            .order_by(BrokerTransaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [t.to_dict() for t in result.scalars().all()]