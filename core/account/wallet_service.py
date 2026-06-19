"""
خدمة المحفظة — WalletOperationsMixin
========================================
عمليات الإيداع والسحب والتجميد ونقاط الولاء.

هذا الـ Mix-in يحتوي على:
    - إيداع وسحب من المحفظة (مع قفل صف PostgreSQL)
    - تجميد وإلغاء تجميد مبالغ
    - كسب واستبدال نقاط الولاء
    - تحديث عداد المشتريات
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from core.account.models import Investor

logger = logging.getLogger(__name__)

LOYALTY_POINTS_PER_EGP = float(os.getenv("LOYALTY_POINTS_PER_EGP", "0.0001"))
# 0.0001 = كل 10,000 جنيه = 1 نقطة ولاء
LOYALTY_REDEEM_RATE = float(os.getenv("LOYALTY_REDEEM_RATE", "10.0"))
# كل نقطة ولاء = 10 جنيه عند الاستبدال


class WalletOperationsMixin:
    """Mix-in: عمليات المحفظة المالية."""

    async def deposit(
        self,
        user_id: str,
        amount: float,
        description: str = "",
        reference_id: str = "",
    ) -> Dict[str, Any]:
        """
        إيداع مبلغ في محفظة المستثمر.

        يستخدم UPDATE ... WHERE مع قفل الصف لضمان التزامن.
        """
        if amount <= 0:
            raise ValueError("مبلغ الإيداع يجب أن يكون موجباً")

        # قفل الصف وقراءة الرصيد الحالي
        stmt = (
            select(Investor)
            .where(Investor.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        if not investor:
            raise ValueError(f"المستثمر {user_id} غير موجود")

        # تحديث الرصيد
        investor.wallet_balance_egp += amount
        investor.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(investor)

        await self._add_transaction(
            user_id=user_id,
            tx_type="deposit",
            amount=amount,
            description=description or "إيداع في المحفظة",
            reference_id=reference_id,
        )

        logger.info(f"إيداع {amount:,.2f} ج.م في محفظة {user_id}")
        return self._wallet_dict(investor)

    async def withdraw(
        self,
        user_id: str,
        amount: float,
        description: str = "",
        reference_id: str = "",
    ) -> Dict[str, Any]:
        """سحب مبلغ من محفظة المستثمر مع قفل الصف."""
        if amount <= 0:
            raise ValueError("مبلغ السحب يجب أن يكون موجباً")

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
            raise ValueError(
                f"الرصيد المتاح غير كافٍ. المتاح: {available:,.2f} ج.م، المطلوب: {amount:,.2f} ج.م"
            )

        investor.wallet_balance_egp -= amount
        investor.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(investor)

        await self._add_transaction(
            user_id=user_id,
            tx_type="withdrawal",
            amount=-amount,
            description=description or "سحب من المحفظة",
            reference_id=reference_id,
        )

        logger.info(f"سحب {amount:,.2f} ج.م من محفظة {user_id}")
        return self._wallet_dict(investor)

    async def freeze_amount(self, user_id: str, amount: float) -> bool:
        """تجميد مبلغ في المحفظة (عند بدء معاملة شراء)."""
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
            raise ValueError(f"الرصيد المتاح غير كافٍ لتجميد {amount:,.2f} ج.م")

        investor.frozen_balance_egp += amount
        investor.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(investor)

        await self._add_transaction(
            user_id=user_id,
            tx_type="freeze",
            amount=amount,
            description=f"تجميد مبلغ {amount:,.2f} ج.م — معاملة شراء قيد التنفيذ",
            reference_id="",
        )

        logger.info(f"تجميد {amount:,.2f} ج.م في محفظة {user_id}")
        return True

    async def unfreeze_amount(self, user_id: str, amount: float) -> bool:
        """إلغاء تجميد مبلغ (عند إلغاء المعاملة)."""
        stmt = (
            select(Investor)
            .where(Investor.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        if not investor:
            return False

        actual_unfreeze = min(amount, investor.frozen_balance_egp)
        investor.frozen_balance_egp -= actual_unfreeze
        investor.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(investor)

        await self._add_transaction(
            user_id=user_id,
            tx_type="unfreeze",
            amount=-actual_unfreeze,
            description=f"إلغاء تجميد {actual_unfreeze:,.2f} ج.م",
            reference_id="",
        )

        logger.info(f"إلغاء تجميد {actual_unfreeze:,.2f} ج.م في محفظة {user_id}")
        return True

    # ─── نقاط الولاء ───

    async def add_loyalty_points(self, user_id: str, spent_amount: float) -> int:
        """
        إضافة نقاط ولاء بناءً على المبلغ المنفق.

        معدل: كل 10,000 ج.م = 1 نقطة ولاء.
        يُستدعى عادةً من داخل transfer_ownership().
        """
        points_earned = int(spent_amount * LOYALTY_POINTS_PER_EGP)
        if points_earned <= 0:
            return 0

        stmt = (
            select(Investor)
            .where(Investor.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        if not investor:
            return 0

        investor.loyalty_points += points_earned
        investor.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(investor)

        await self._add_transaction(
            user_id=user_id,
            tx_type="loyalty_earn",
            amount=0.0,
            description=f"كسب {points_earned} نقطة ولاء من شراء بقيمة {spent_amount:,.2f} ج.م",
            reference_id="",
        )

        logger.info(f"كسب المستثمر {user_id} عدد {points_earned} نقطة ولاء")
        return points_earned

    async def redeem_loyalty_points(self, user_id: str, points: int) -> float:
        """
        استبدال نقاط الولاء برصيد في المحفظة.

        معدل: كل نقطة = 10 ج.م.
        """
        if points <= 0:
            raise ValueError("عدد النقاط يجب أن يكون موجباً")

        stmt = (
            select(Investor)
            .where(Investor.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        if not investor:
            raise ValueError(f"المستثمر {user_id} غير موجود")

        if investor.loyalty_points < points:
            raise ValueError(
                f"نقاط الولاء غير كافية. المتاح: {investor.loyalty_points}, المطلوب: {points}"
            )

        egp_amount = points * LOYALTY_REDEEM_RATE
        investor.loyalty_points -= points
        investor.wallet_balance_egp += egp_amount
        investor.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(investor)

        await self._add_transaction(
            user_id=user_id,
            tx_type="loyalty_redeem",
            amount=egp_amount,
            description=f"استبدال {points} نقطة ولاء = {egp_amount:,.2f} ج.م",
            reference_id="",
        )

        logger.info(f"استبدال المستثمر {user_id} عدد {points} نقطة = {egp_amount:,.2f} ج.م")
        return egp_amount

    # ─── تحديث إحصائيات الشراء ───

    async def increment_purchased(self, user_id: str, amount_spent: float) -> None:
        """زيادة عداد الأراضي المشتراة — يُستدعى من transfer_ownership()."""
        stmt = (
            update(Investor)
            .where(Investor.user_id == user_id)
            .values(
                total_lands_purchased=Investor.total_lands_purchased + 1,
                total_spent_egp=Investor.total_spent_egp + amount_spent,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)
