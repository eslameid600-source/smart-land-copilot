"""
معالج الدفع — PaymentProcessor (Async + PostgreSQL)
=====================================================
معاملة شراء أرض كاملة — خطوة واحدة.

الخطوات:
1. إنشاء معاملة فريدة + حماية التكرار
2. إنشاء فاتورة في بوابة الدفع
3. حفظ المعاملة مع حالة PENDING في PostgreSQL
4. إرجاع رابط الدفع للمستخدم
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from payment.idempotency_provider import IdempotencyProvider
from payment.models import PaymentTransaction
from payment.transaction_store import TransactionStore
from payment.wallet_store import WalletStore
from sqlalchemy.ext.asyncio import AsyncSession

from core.financial.base import PaymentItem, PaymentRequest, PaymentRouter

logger = logging.getLogger(__name__)


class PaymentProcessor:
    """
    معالج المعاملات الرئيسية — ينشئ فاتورة ويحفظ المعاملة في PostgreSQL.

    كل العمليات async وتأخذ session: AsyncSession.
    """

    def __init__(
        self,
        session: AsyncSession,
        router: PaymentRouter,
        wallets: WalletStore,
        transactions: TransactionStore,
        idempotency: IdempotencyProvider,
    ):
        self.session = session
        self.router = router
        self.wallets = wallets
        self.transactions = transactions
        self.idempotency = idempotency

    async def process_transaction(
        self,
        land_id: str,
        buyer_id: str,
        seller_id: str,
        amount: float,
        gateway: str = "fawry",
        currency: str = "EGP",
        description: str = "",
        buyer_name: str = "",
        buyer_email: str = "",
        buyer_phone: str = "",
        items: Optional[List[PaymentItem]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """
        معاملة شراء أرض كاملة — خطوة واحدة (async).

        Returns:
            {
                "transaction_id": str,
                "payment_url": str,
                "status": str,
                "gateway": str,
                "amount": float,
            }

        Raises:
            ValueError: مبلغ غير صالح
            SecurityError: تكرار محاول الدفع
        """
        # ── التحقق من المدخلات ──
        if amount <= 0:
            raise ValueError(f"المبلغ يجب أن يكون موجباً: {amount}")

        if not land_id or not buyer_id or not seller_id:
            raise ValueError("land_id و buyer_id و seller_id مطلوبون")

        if buyer_id == seller_id:
            raise ValueError("المشتري والبائع لا يمكن أن يكونوا نفس المستخدم")

        # ── حماية التكرار ──
        existing_txn_id = await self.idempotency.check_and_register(idempotency_key)
        if existing_txn_id:
            existing = await self.transactions.get(existing_txn_id)
            if existing:
                logger.info(
                    "معاملة مكررة — idempotency: %s → txn: %s",
                    idempotency_key, existing_txn_id,
                )
                gw_resp = {}
                if existing.gateway_response:
                    try:
                        gw_resp = json.loads(existing.gateway_response)
                    except (json.JSONDecodeError, TypeError):
                        pass
                return {
                    "transaction_id": existing_txn_id,
                    "payment_url": gw_resp.get("payment_url", ""),
                    "status": existing.status,
                    "gateway": existing.gateway_type,
                    "amount": existing.amount,
                    "is_duplicate": True,
                }

        # ── إنشاء معاملة ──
        transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        # أرصدة قبل المعاملة
        buyer_balance_before = await self.wallets.get_balance(buyer_id)
        seller_balance_before = await self.wallets.get_balance(seller_id)

        # بناء طلب الدفع
        payment_request = PaymentRequest(
            merchant_ref=transaction_id,
            amount=amount,
            currency=currency,
            description=description or f"دفعة شراء أرض — {land_id}",
            customer_name=buyer_name,
            customer_email=buyer_email,
            customer_phone=buyer_phone,
            items=items or [PaymentItem(
                item_id=land_id,
                description=f"شراء أرض — {land_id}",
                quantity=1,
                price_per_unit=amount,
            )],
            metadata=metadata or {},
            idempotency_key=idempotency_key or transaction_id,
        )

        # ── إنشاء الفاتورة في البوابة ──
        payment_result = self.router.initiate_payment(gateway, payment_request)

        # ── إنشاء سجل المعاملة في PostgreSQL ──
        meta = {**(metadata or {}), "payment_url": payment_result.payment_url}
        if payment_result.gateway_response:
            meta["gateway_response"] = payment_result.gateway_response

        txn = PaymentTransaction(
            transaction_id=transaction_id,
            land_id=land_id,
            buyer_id=buyer_id,
            seller_id=seller_id,
            amount=amount,
            currency=currency,
            status="pending",
            gateway_type=gateway,
            transaction_type="purchase",
            gateway_ref=payment_result.transaction_ref,
            gateway_response=json.dumps(payment_result.gateway_response, ensure_ascii=False),
            buyer_balance_before=buyer_balance_before,
            buyer_balance_after=buyer_balance_before,
            seller_balance_before=seller_balance_before,
            seller_balance_after=seller_balance_before,
            description=description,
            metadata_json=json.dumps(meta, ensure_ascii=False),
        )

        await self.transactions.save(txn)

        # حفظ مفتاح idempotency
        if idempotency_key:
            await self.idempotency.register(idempotency_key, transaction_id)

        # تحديث الحالة إذا فشل إنشاء الفاتورة
        if not payment_result.success:
            await self.transactions.update_status(transaction_id, "failed")

        logger.info(
            "معاملة جديدة: %s — %.2f %s — %s — بوابة: %s — URL: %s",
            transaction_id, amount, currency,
            "نجح" if payment_result.success else "فشل",
            gateway,
            payment_result.payment_url[:80] if payment_result.payment_url else "لا يوجد",
        )

        return {
            "transaction_id": transaction_id,
            "payment_url": payment_result.payment_url,
            "status": payment_result.status.value,
            "gateway": gateway,
            "amount": amount,
            "currency": currency,
            "error": payment_result.error_message if not payment_result.success else None,
        }