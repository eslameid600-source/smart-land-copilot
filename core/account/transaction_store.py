"""
مخزن المعاملات — TransactionStore (PostgreSQL)
==================================================
تخزين واسترجاع معاملات الدفع عبر payment_transactions table.

يستخدم AsyncSession + SQLAlchemy ORM.
لا حاجة لـ threading.Lock — PostgreSQL يتكفل بالتزامن.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from payment.models import PaymentTransaction

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """التاريخ والوقت الحالي بصيغة ISO."""
    return datetime.now(timezone.utc).isoformat()


class TransactionStore:
    """
    تخزين واسترجاع معاملات الدفع — PostgreSQL-backed.

    كل عملية تأخذ session: AsyncSession.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, txn: PaymentTransaction) -> None:
        """حفظ معاملة جديدة."""
        self.session.add(txn)
        await self.session.flush()
        await self.session.refresh(txn)

    async def get(self, transaction_id: str) -> Optional[PaymentTransaction]:
        """استرجاع معاملة بمعرّفها العام (transaction_id مثل TXN-xxx)."""
        stmt = (
            select(PaymentTransaction)
            .where(PaymentTransaction.transaction_id == transaction_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_land(self, land_id: str) -> List[PaymentTransaction]:
        """جميع معاملات أرض (الأحدث أولاً)."""
        stmt = (
            select(PaymentTransaction)
            .where(PaymentTransaction.land_id == land_id)
            .order_by(PaymentTransaction.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_buyer(self, buyer_id: str) -> List[PaymentTransaction]:
        """جميع معاملات مشترٍ (الأحدث أولاً)."""
        stmt = (
            select(PaymentTransaction)
            .where(PaymentTransaction.buyer_id == buyer_id)
            .order_by(PaymentTransaction.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_seller(self, seller_id: str) -> List[PaymentTransaction]:
        """جميع معاملات بائع (الأحدث أولاً)."""
        stmt = (
            select(PaymentTransaction)
            .where(PaymentTransaction.seller_id == seller_id)
            .order_by(PaymentTransaction.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, transaction_id: str, status: str,
    ) -> None:
        """تحديث حالة معاملة."""
        values = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }
        if status == "completed":
            values["completed_at"] = datetime.now(timezone.utc)

        stmt = (
            update(PaymentTransaction)
            .where(PaymentTransaction.transaction_id == transaction_id)
            .values(**values)
        )
        await self.session.execute(stmt)

    async def get_pending_count(self, buyer_id: str) -> int:
        """عدد المعاملات المعلقة لمشترٍ."""
        stmt = (
            select(func.count())
            .select_from(PaymentTransaction)
            .where(
                PaymentTransaction.buyer_id == buyer_id,
                PaymentTransaction.status == "pending",
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def list_all(self, limit: int = 50) -> List[PaymentTransaction]:
        """قائمة جميع المعاملات (الأحدث أولاً)."""
        stmt = (
            select(PaymentTransaction)
            .order_by(PaymentTransaction.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_after_webhook(
        self,
        transaction_id: str,
        status: str,
        gateway_ref: Optional[str] = None,
        buyer_balance_after: Optional[float] = None,
        seller_balance_after: Optional[float] = None,
        refunded_amount: Optional[float] = None,
        loyalty_points: int = 0,
    ) -> None:
        """
        تحديث شامل للمعاملة بعد webhook.

        يُستدعى من WebhookHandler لتحديث الحالة والأرصدة دفعة واحدة.
        """
        values: Dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }

        if status == "completed":
            values["completed_at"] = datetime.now(timezone.utc)
        if gateway_ref:
            values["gateway_ref"] = gateway_ref
        if buyer_balance_after is not None:
            values["buyer_balance_after"] = buyer_balance_after
        if seller_balance_after is not None:
            values["seller_balance_after"] = seller_balance_after
        if refunded_amount is not None:
            values["refunded_amount"] = refunded_amount
        if loyalty_points > 0:
            values["loyalty_points_earned"] = loyalty_points

        stmt = (
            update(PaymentTransaction)
            .where(PaymentTransaction.transaction_id == transaction_id)
            .values(**values)
        )
        await self.session.execute(stmt)