"""
مخزن المعاملات — TransactionMixin + إحصائيات
================================================
سجل معاملات المحفظة + إحصائيات المنصة.

هذا الملف يحتوي على:
    - TransactionMixin: استرجاع سجل المعاملات وإضافة معاملات جديدة
    - get_platform_stats(): إحصائيات عامة للمنصة (لوحة التحكم)
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.account.models import Investor, Landowner, WalletTransaction

logger = logging.getLogger(__name__)


class TransactionMixin:
    """Mix-in: سجل معاملات المحفظة."""

    async def get_transactions(
        self,
        user_id: str,
        tx_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """استرجاع سجل معاملات المحفظة (الأحدث أولاً)."""
        stmt = (
            select(WalletTransaction)
            .where(WalletTransaction.investor_id == user_id)
        )
        if tx_type:
            stmt = stmt.where(WalletTransaction.tx_type == tx_type)
        stmt = stmt.order_by(WalletTransaction.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return [tx.to_dict() for tx in result.scalars().all()]

    # ─── دوال مساعدة داخلية ───

    async def _add_transaction(
        self,
        user_id: str,
        tx_type: str,
        amount: float,
        description: str,
        reference_id: str,
    ) -> WalletTransaction:
        """إضافة معاملة لسجل المحفظة."""
        # قراءة الرصيد الحالي
        stmt = select(Investor.wallet_balance_egp).where(Investor.user_id == user_id)
        result = await self.session.execute(stmt)
        balance = result.scalar_one_or_none() or 0.0

        tx = WalletTransaction(
            investor_id=user_id,
            tx_type=tx_type,
            amount_egp=amount,
            balance_after=balance,
            description=description,
            reference_id=reference_id,
        )
        self.session.add(tx)
        return tx


# ─── إحصائيات عامة ───

async def get_platform_stats(session: AsyncSession) -> Dict[str, Any]:
    """
    إحصائيات المنصة العامة — تُستخدم في لوحة التحكم.

    Returns:
        {
            "total_investors": int,
            "total_landowners": int,
            "total_wallet_balance_egp": float,
            "total_transactions": int,
            "total_loyalty_points": int,
        }
    """
    # عداد المستثمرين
    inv_count_stmt = select(func.count()).select_from(Investor)
    inv_count = (await session.execute(inv_count_stmt)).scalar() or 0

    # عداد الملاك
    lo_count_stmt = select(func.count()).select_from(Landowner)
    lo_count = (await session.execute(lo_count_stmt)).scalar() or 0

    # إجمالي الأرصدة
    total_balance_stmt = select(func.coalesce(func.sum(Investor.wallet_balance_egp), 0))
    total_balance = (await session.execute(total_balance_stmt)).scalar() or 0.0

    # إجمالي المعاملات
    tx_count_stmt = select(func.count()).select_from(WalletTransaction)
    tx_count = (await session.execute(tx_count_stmt)).scalar() or 0

    # إجمالي نقاط الولاء
    total_loyalty_stmt = select(func.coalesce(func.sum(Investor.loyalty_points), 0))
    total_loyalty = (await session.execute(total_loyalty_stmt)).scalar() or 0

    return {
        "total_investors": inv_count,
        "total_landowners": lo_count,
        "total_wallet_balance_egp": round(total_balance, 2),
        "total_transactions": tx_count,
        "total_loyalty_points": int(total_loyalty),
    }
