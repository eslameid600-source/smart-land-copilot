"""
مخزن المستثمرين — InvestorCrudMixin
=====================================
قراءة وكتابة بيانات المستثمرين (CRUD) + بيانات المحفظة الأساسية.

هذا الـ Mix-in يحتوي على:
    - إنشاء حساب مستثمر جديد
    - استرجاع بيانات مستثمر (واحد / جميع)
    - التحقق من الوجود والعدد
    - بيانات المحفظة الكاملة
    - دالة مساعدة لبناء قاموس المحفظة
"""
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.account.models import Investor, WalletTransaction

logger = logging.getLogger(__name__)


class InvestorCrudMixin:
    """Mix-in: عمليات CRUD للمستثمر + بيانات المحفظة."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ─── إنشاء حساب مستثمر ───

    async def create(
        self,
        user_id: str,
        full_name_ar: str = "",
        initial_deposit: float = 0.0,
    ) -> Dict[str, Any]:
        """
        إنشاء حساب مستثمر جديد.

        Args:
            user_id: معرّف المستخدم من خدمة المصادقة
            full_name_ar: الاسم بالعربية
            initial_deposit: الإيداع الأولي (الافتراضي: 0)

        Returns:
            بيانات المستثمر المنشأ

        Raises:
            ValueError: إذا كان المستثمر موجوداً مسبقاً
        """
        # التحقق من عدم التكرار
        existing = await self.get(user_id)
        if existing:
            raise ValueError(f"المستثمر {user_id} مسجل مسبقاً")

        investor = Investor(
            user_id=user_id,
            full_name_ar=full_name_ar or None,
            wallet_balance_egp=float(initial_deposit),
        )
        self.session.add(investor)
        await self.session.flush()  # يُحصل على الـ id
        await self.session.refresh(investor)

        # سجل إيداع أولي إن وُجد
        if initial_deposit > 0:
            await self._add_transaction(
                user_id=user_id,
                tx_type="deposit",
                amount=initial_deposit,
                description="إيداع أولي عند إنشاء الحساب",
                reference_id="",
            )

        logger.info(f"تم إنشاء حساب مستثمر: {user_id} (إيداع أولي: {initial_deposit:,.2f} ج.م)")
        return investor.to_dict()

    # ─── استرجاع بيانات ───

    async def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع بيانات مستثمر واحد."""
        stmt = select(Investor).where(Investor.user_id == user_id)
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        return investor.to_dict() if investor else None

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """استرجاع جميع المستثمرين مع دعم التصفح."""
        stmt = (
            select(Investor)
            .order_by(Investor.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [inv.to_dict() for inv in result.scalars().all()]

    async def exists(self, user_id: str) -> bool:
        """التحقق من وجود مستثمر."""
        stmt = select(func.count()).select_from(Investor).where(Investor.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar() > 0

    async def count(self) -> int:
        """عدد المستثمرين المسجلين."""
        stmt = select(func.count()).select_from(Investor)
        result = await self.session.execute(stmt)
        return result.scalar()

    # ─── بيانات المحفظة ───

    async def get_wallet(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        بيانات المحفظة الكاملة لمستثمر.

        Returns:
            {
                "user_id", "wallet_balance_egp", "frozen_balance_egp",
                "available_balance_egp", "loyalty_points",
                "total_lands_purchased", "total_spent_egp",
                "last_transaction_at"
            }
            أو None إذا لم يُوجد المستثمر.
        """
        stmt = select(Investor).where(Investor.user_id == user_id)
        result = await self.session.execute(stmt)
        investor = result.scalar_one_or_none()
        if not investor:
            return None

        # آخر معاملة
        last_tx_stmt = (
            select(WalletTransaction.created_at)
            .where(WalletTransaction.investor_id == user_id)
            .order_by(WalletTransaction.created_at.desc())
            .limit(1)
        )
        last_tx_result = await self.session.execute(last_tx_stmt)
        last_tx_row = last_tx_result.scalar_one_or_none()
        last_tx_time = last_tx_row.isoformat() if last_tx_row else None

        return {
            "user_id": user_id,
            "wallet_balance_egp": investor.wallet_balance_egp,
            "frozen_balance_egp": investor.frozen_balance_egp,
            "available_balance_egp": investor.available_balance_egp,
            "loyalty_points": investor.loyalty_points,
            "total_lands_purchased": investor.total_lands_purchased,
            "total_spent_egp": investor.total_spent_egp,
            "last_transaction_at": last_tx_time,
        }

    # ─── دوال مساعدة داخلية ───

    def _wallet_dict(self, investor: Investor) -> Dict[str, Any]:
        """بناء قاموس المحفظة من كائن Investor."""
        return {
            "user_id": investor.user_id,
            "wallet_balance_egp": investor.wallet_balance_egp,
            "frozen_balance_egp": investor.frozen_balance_egp,
            "available_balance_egp": investor.available_balance_egp,
            "loyalty_points": investor.loyalty_points,
            "total_lands_purchased": investor.total_lands_purchased,
            "total_spent_egp": investor.total_spent_egp,
        }
