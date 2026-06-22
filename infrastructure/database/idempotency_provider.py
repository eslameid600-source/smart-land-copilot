"""
مزود حماية التكرار — IdempotencyProvider (PostgreSQL)
========================================================
يمنع تكرار المعاملات عبر جدول idempotency_keys.

لا حاجة لـ threading.Lock — UNIQUE constraint في PostgreSQL
يتكفل بمنع التكرار على مستوى قاعدة البيانات.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from payment.models import IdempotencyKey

logger = logging.getLogger(__name__)


class IdempotencyProvider:
    """
    حماية من تكرار المعاملات — PostgreSQL-backed.

    كل عملية تأخذ session: AsyncSession.
    يُستخدم UNIQUE constraint لمنع التكرار على مستوى DB.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_and_register(self, key: str) -> Optional[str]:
        """
        يتحقق من المفتاح ويسجله إن كان جديداً.

        المخرجات:
            transaction_id إذا كان المفتاح موجوداً مسبقاً (مكرر)
            None إذا كان جديداً (تم التسجيل)
        """
        if not key:
            return None

        # البحث عن المفتاح
        stmt = select(IdempotencyKey).where(IdempotencyKey.key == key)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            return existing.transaction_id

        # تسجيل مفتاح جديد (placeholder — يُحدَّث لاحقاً)
        new_key = IdempotencyKey(key=key, transaction_id="")
        self.session.add(new_key)
        try:
            await self.session.flush()
        except IntegrityError:
            # مفتاح مكرر — قاعدة البيانات رفضته (race condition)
            await self.session.rollback()
            # إعادة القراءة
            result2 = await self.session.execute(stmt)
            existing2 = result2.scalar_one_or_none()
            return existing2.transaction_id if existing2 else None

        return None

    async def register(self, key: str, transaction_id: str) -> None:
        """ربط مفتاح idempotency بمعرف المعاملة."""
        if not key:
            return

        stmt = select(IdempotencyKey).where(IdempotencyKey.key == key)
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if record:
            record.transaction_id = transaction_id
            await self.session.flush()

    async def get_existing(self, key: str) -> Optional[str]:
        """استرجاع معرف المعاملة لمفتاح."""
        if not key:
            return None
        stmt = select(IdempotencyKey.transaction_id).where(IdempotencyKey.key == key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()