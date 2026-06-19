"""
مخزن المحافظ — WalletStore (PostgreSQL)
==========================================
إدارة أرصدة المحافظ عبر Investor table + AsyncSession.

يُفوّض كل العمليات إلى جدول investors في PostgreSQL
بدلاً من الذاكرة الداخلية و threading.Lock.

التزامن: PostgreSQL row-level locks (SELECT ... FOR UPDATE).
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.account.models import Investor

logger = logging.getLogger(__name__)

_MIN_BALANCE = float(os.environ.get("WALLET_MIN_BALANCE", "0"))


class WalletStore:
    """
    إدارة أرصدة المحافظ — PostgreSQL-backed عبر AsyncSession.

    كل عملية تأخذ session: AsyncSession كمعامل أول.
    التزامن يُدار عبر SELECT ... FOR UPDATE بدلاً من threading.Lock.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_balance(self, user_id: str) -> float:
        """استرجاع الرصيد الكلي للمستخدم."""
        stmt = select(Investor.wallet_balance_egp).where(Investor.user_id == user_id)
        result = await self.session.execute(stmt)
        balance = result.scalar_one_or_none()
        return float(balance) if balance is not None else 0.0

    async def get_wallet(self, user_id: str) -> Dict[str, Any]:
        """استرجاع بيانات المحفظة الكاملة."""
        stmt = select(Investor).where(Investor.user_id == user_id)
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        if not investor:
            return {"balance": 0.0, "currency": "EGP", "frozen": 0.0, "available": 0.0}
        return {
            "balance": investor.wallet_balance_egp,
            "currency": "EGP",
            "frozen": investor.frozen_balance_egp,
            "available": investor.available_balance_egp,
        }

    async def deposit(
        self, user_id: str, amount: float, transaction_id: str = "",
    ) -> float:
        """
        إيداع مبلغ في المحفظة — مع قفل الصف.

        Returns:
            الرصيد الجديد بعد الإيداع
        """
        if amount <= 0:
            raise ValueError(f"مبلغ الإيداع يجب أن يكون موجباً: {amount}")

        stmt = (
            select(Investor)
            .where(Investor.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()

        if not investor:
            # إنشاء حساب مستثمر تلقائياً إن لم يكن موجوداً
            from core.account.models import _generate_uuid
            investor = Investor(
                id=_generate_uuid(),
                user_id=user_id,
                wallet_balance_egp=amount,
            )
            self.session.add(investor)
            await self.session.flush()
            await self.session.refresh(investor)
        else:
            investor.wallet_balance_egp += amount
            investor.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(investor)

        new_balance = investor.wallet_balance_egp
        logger.info(
            "إيداع %.2f في محفظة %s — رصيد جديد: %.2f (معاملة: %s)",
            amount, user_id, new_balance, transaction_id,
        )
        return new_balance

    async def withdraw(
        self, user_id: str, amount: float, transaction_id: str = "",
    ) -> float:
        """
        سحب مبلغ من المحفظة — مع قفل الصف.

        Raises:
            ValueError: إذا كان الرصيد غير كافٍ

        Returns:
            الرصيد الجديد بعد السحب
        """
        if amount <= 0:
            raise ValueError(f"مبلغ السحب يجب أن يكون موجباً: {amount}")

        stmt = (
            select(Investor)
            .where(Investor.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        if not investor:
            investor = Investor(user_id=user_id)
            self.session.add(investor)
            await self.session.flush()
            await self.session.refresh(investor)

        available = investor.available_balance_egp
        if available < amount + _MIN_BALANCE:
            raise ValueError(
                f"رصيد غير كافٍ: متاح={available:.2f}, مطلوب={amount:.2f}, "
                f"حد أدنى={_MIN_BALANCE:.2f}"
            )

        investor.wallet_balance_egp -= amount
        investor.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(investor)

        new_balance = investor.wallet_balance_egp
        logger.info(
            "سحب %.2f من محفظة %s — رصيد جديد: %.2f (معاملة: %s)",
            amount, user_id, new_balance, transaction_id,
        )
        return new_balance

    async def freeze(self, user_id: str, amount: float) -> None:
        """تجميد مبلغ في المحفظة (مثلاً أثناء مزاد) — مع قفل الصف."""
        stmt = (
            select(Investor)
            .where(Investor.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        if not investor:
            raise ValueError(f"المستثمر {user_id} غير موجود")

        available = investor.available_balance_egp
        if available < amount:
            raise ValueError("رصيد غير كافٍ للتجميد")

        investor.frozen_balance_egp += amount
        investor.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(investor)

    async def unfreeze(self, user_id: str, amount: float) -> None:
        """إلغاء تجميد مبلغ — مع قفل الصف."""
        stmt = (
            select(Investor)
            .where(Investor.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        if not investor:
            return

        actual_unfreeze = min(amount, investor.frozen_balance_egp)
        if actual_unfreeze <= 0:
            return

        investor.frozen_balance_egp -= actual_unfreeze
        investor.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(investor)

    async def transfer(
        self,
        from_user: str,
        to_user: str,
        amount: float,
        transaction_id: str = "",
    ) -> Dict[str, float]:
        """
        تحويل مبلغ بين محفظتين — ذري مع قفل صفّين.

        Raises:
            ValueError: إذا كان رصيد المُرسل غير كافٍ

        Returns:
            {"from_balance": float, "to_balance": float}
        """
        if amount <= 0:
            raise ValueError("مبلغ التحويل يجب أن يكون موجباً")

        # قفل صف المُرسل
        sender_stmt = (
            select(Investor)
            .where(Investor.user_id == from_user)
            .with_for_update()
        )
        sender_result = await self.session.execute(sender_stmt)
        sender = sender_result.scalar_one_or_none()
        if not sender:
            sender = Investor(user_id=from_user)
            self.session.add(sender)
            await self.session.flush()

        # قفل صف المُستقبل
        receiver_stmt = (
            select(Investor)
            .where(Investor.user_id == to_user)
            .with_for_update()
        )
        receiver_result = await self.session.execute(receiver_stmt)
        receiver = receiver_result.scalar_one_or_none()
        if not receiver:
            receiver = Investor(user_id=to_user)
            self.session.add(receiver)
            await self.session.flush()

        # التحقق من رصيد المُرسل
        available = sender.available_balance_egp
        if available < amount + _MIN_BALANCE:
            raise ValueError(f"رصيد المُرسل غير كافٍ: {available:.2f}")

        # تنفيذ التحويل
        sender.wallet_balance_egp -= amount
        sender.updated_at = datetime.now(timezone.utc)

        receiver.wallet_balance_egp += amount
        receiver.updated_at = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(sender)
        await self.session.refresh(receiver)

        logger.info(
            "تحويل %.2f من %s إلى %s (معاملة: %s)",
            amount, from_user, to_user, transaction_id,
        )

        return {
            "from_balance": sender.wallet_balance_egp,
            "to_balance": receiver.wallet_balance_egp,
        }

    async def get_all_balances(self) -> Dict[str, float]:
        """جميع الأرصدة (للإدارة)."""
        stmt = select(Investor.user_id, Investor.wallet_balance_egp)
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}