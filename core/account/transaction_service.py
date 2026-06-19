"""
خدمة المعاملات والمحافظ — نقطة الدخول الموحدة (PostgreSQL)
================================================================
يعيد تصدير كل الواجهات من الوحدات الفرعية.

ملاحظة مهمة: جميع المكونات الآن تعمل مع PostgreSQL عبر AsyncSession.
يجب تمرير session عند إنشاء كل مكون.

الاستخدام:
    from infrastructure.database import get_session
    from payment.transaction_service import TransactionService

    async with get_session() as session:
        svc = TransactionService(session=session)
        result = await svc.process_transaction(
            land_id="EG-CAI-01",
            buyer_id="user-001",
            seller_id="owner-001",
            amount=1_000_000,
        )
"""
from payment.wallet_store import WalletStore
from payment.transaction_store import TransactionStore, _now_iso
from payment.idempotency_provider import IdempotencyProvider
from payment.payment_processor import PaymentProcessor
from payment.webhook_handler import WebhookHandler
from payment.refund_manager import RefundManager

from core.financial.base import (
    PaymentRouter, TransactionStatus, RefundResult,
    Transaction, TransactionType, PaymentGatewayType,
    PaymentItem,
)


class TransactionService:
    """
    خدمة المعاملات — تُركَّب من مكونات PostgreSQL-backed.

    يحتفظ بالواجهة الأصلية للتوافقية.
    كل العمليات الآن async وتستخدم AsyncSession.
    """

    def __init__(self, session, router=None):
        """
        إنشاء خدمة المعاملات.

        Args:
            session: AsyncSession نشط (مطلوب)
            router: PaymentRouter (اختياري — يُنشأ فارغاً إن لم يُمرر)
        """
        self.session = session
        self.router = router or PaymentRouter()

        # إنشاء المكونات مع session
        self.wallets = WalletStore(session)
        self.transactions = TransactionStore(session)
        self.idempotency = IdempotencyProvider(session)

        self.processor = PaymentProcessor(
            session=session,
            router=self.router,
            wallets=self.wallets,
            transactions=self.transactions,
            idempotency=self.idempotency,
        )
        self.webhook_handler = WebhookHandler(
            session=session,
            router=self.router,
            wallets=self.wallets,
            transactions=self.transactions,
        )
        self.refund_manager = RefundManager(
            session=session,
            router=self.router,
            wallets=self.wallets,
            transactions=self.transactions,
            webhook_handler=self.webhook_handler,
        )

    # ─── واجهات التوافقية (async) ───

    async def process_transaction(self, *args, **kwargs):
        """معاملة شراء أرض — async."""
        return await self.processor.process_transaction(*args, **kwargs)

    async def handle_webhook(self, *args, **kwargs):
        """معالجة webhook — async."""
        return await self.webhook_handler.handle_webhook(*args, **kwargs)

    async def refund_transaction(self, *args, **kwargs):
        """استرداد مبلغ — async."""
        return await self.refund_manager.refund_transaction(*args, **kwargs)

    async def get_transaction(self, *args, **kwargs):
        """استرجاع معاملة — async."""
        return await self.refund_manager.get_transaction(*args, **kwargs)

    async def get_buyer_transactions(self, *args, **kwargs):
        """معاملات مشترٍ — async."""
        return await self.refund_manager.get_buyer_transactions(*args, **kwargs)

    async def get_land_transactions(self, *args, **kwargs):
        """معاملات أرض — async."""
        return await self.refund_manager.get_land_transactions(*args, **kwargs)

    async def get_buyer_summary(self, *args, **kwargs):
        """ملخص مشترٍ — async."""
        return await self.refund_manager.get_buyer_summary(*args, **kwargs)


__all__ = [
    "WalletStore", "TransactionStore", "IdempotencyProvider",
    "PaymentProcessor", "WebhookHandler", "RefundManager",
    "TransactionService", "_now_iso",
]