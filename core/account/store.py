"""
مخزن الحسابات — نقطة الدخول الموحدة
========================================
يعيد تصدير كل الواجهات من الوحدات الفرعية.
هذا الملف موجود للتوافقية مع الاستيرادات القديمة.

الاستخدام:
    from core.account.store import InvestorStore, LandownerStore, transfer_ownership

    async with get_session() as session:
        inv_store = InvestorStore(session)
        await inv_store.create(user_id="inv-001", initial_deposit=500_000)
"""
from core.account.investor_repository import InvestorCrudMixin
from core.account.landowner_repository import LandownerStore
from core.account.transaction_repository import TransactionMixin, get_platform_stats
from core.account.transfer_service import (
    PLATFORM_COMMISSION_PCT,
    InvestorStore,
    transfer_ownership,
)
from core.account.wallet_service import (
    LOYALTY_POINTS_PER_EGP,
    LOYALTY_REDEEM_RATE,
    WalletOperationsMixin,
)

__all__ = [
    "InvestorStore",
    "LandownerStore",
    "transfer_ownership",
    "get_platform_stats",
    "InvestorCrudMixin",
    "WalletOperationsMixin",
    "TransactionMixin",
    "LOYALTY_POINTS_PER_EGP",
    "LOYALTY_REDEEM_RATE",
    "PLATFORM_COMMISSION_PCT",
]
