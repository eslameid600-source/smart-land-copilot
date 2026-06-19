"""
معالج Webhooks — WebhookHandler (Async + PostgreSQL)
========================================================
معالجة أحداث الدفع من البوابات الخارجية.

الخطوات:
1. التحقق من التوقيع (الأمان)
2. تحليل الحدث
3. البحث عن المعاملة في PostgreSQL
4. تحديث الحالة والأرصدة في DB
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.financial.base import (
    PaymentRouter, TransactionStatus,
)
from payment.models import PaymentTransaction
from payment.wallet_store import WalletStore
from payment.transaction_store import TransactionStore

logger = logging.getLogger(__name__)


class WebhookHandler:
    """
    معالج Webhooks — يتحقق من التوقيع ويحدث الأرصدة في PostgreSQL.

    كل العمليات async.
    """

    def __init__(
        self,
        session: AsyncSession,
        router: PaymentRouter,
        wallets: WalletStore,
        transactions: TransactionStore,
    ):
        self.session = session
        self.router = router
        self.wallets = wallets
        self.transactions = transactions
        self._loyalty_rate = float(os.environ.get("LOYALTY_POINTS_PER_EGP", "0.0001"))

    async def handle_webhook(
        self,
        gateway: str,
        payload: bytes,
        signature: str,
        parsed_body: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        معالجة Webhook من بوابة دفع (async).

        Returns:
            dict مع تفاصيل المعالجة
        """
        # 1 + 2: التحقق + التحليل
        event = self.router.handle_webhook(gateway, payload, signature, parsed_body)
        status = event["status"]
        merchant_ref = event["merchant_ref"]
        amount = event.get("amount", 0.0)

        # 3: البحث عن المعاملة في DB
        txn = await self.transactions.get(merchant_ref)
        if not txn:
            logger.warning(
                "Webhook: معاملة غير موجودة — مرجع: %s — حالة: %s",
                merchant_ref, status,
            )
            return {
                "processed": False,
                "reason": "المعاملة غير موجودة",
                "merchant_ref": merchant_ref,
            }

        old_status = txn.status
        gateway_ref = event.get("gateway_ref")

        # ── تنفيذ الإجراءات حسب الحالة ──
        if status == TransactionStatus.COMPLETED and old_status != TransactionStatus.COMPLETED:
            loyalty_points = await self._complete_transaction(txn, amount)
            await self.transactions.update_after_webhook(
                transaction_id=merchant_ref,
                status="completed",
                gateway_ref=gateway_ref,
                buyer_balance_after=txn.buyer_balance_after,
                seller_balance_after=txn.seller_balance_after,
                loyalty_points=loyalty_points,
            )

        elif status == TransactionStatus.FAILED:
            await self.transactions.update_after_webhook(
                transaction_id=merchant_ref,
                status="failed",
            )

        elif status in (TransactionStatus.REFUNDED, TransactionStatus.PARTIALLY_REFUNDED):
            await self._process_refund(txn, amount, status.value)
            await self.transactions.update_after_webhook(
                transaction_id=merchant_ref,
                status=status.value,
                gateway_ref=gateway_ref,
                buyer_balance_after=txn.buyer_balance_after,
                seller_balance_after=txn.seller_balance_after,
                refunded_amount=txn.refunded_amount,
            )

        elif status == TransactionStatus.CANCELLED:
            await self.transactions.update_status(merchant_ref, "cancelled")

        logger.info(
            "Webhook معالج: %s — %s → %s — مبلغ: %.2f",
            merchant_ref, old_status, status.value, amount,
        )

        buyer_balance = await self.wallets.get_balance(txn.buyer_id)
        seller_balance = await self.wallets.get_balance(txn.seller_id)

        return {
            "processed": True,
            "transaction_id": txn.transaction_id,
            "old_status": old_status,
            "new_status": status.value,
            "amount": amount,
            "buyer_balance": buyer_balance,
            "seller_balance": seller_balance,
        }

    async def _complete_transaction(
        self, txn: PaymentTransaction, paid_amount: float,
    ) -> int:
        """
        إكمال المعاملة الناجحة — تحديث الأرصدة في DB.

        Returns:
            عدد نقاط الولاء المكتسبة
        """
        loyalty_points = 0

        # تحديث رصيد المشتري (الشراء يُسجّل كـ withdrawal من المحفظة)
        try:
            new_buyer_balance = await self.wallets.withdraw(
                txn.buyer_id, txn.amount, txn.transaction_id,
            )
            txn.buyer_balance_after = new_buyer_balance
        except ValueError:
            # قد لا يكون الرصيد في المحفظة — الدفع كان من البوابة مباشرة
            txn.buyer_balance_after = await self.wallets.get_balance(txn.buyer_id)
            logger.info(
                "المشتري %s ليس لديه رصيد كافٍ في المحفظة — الدفع كان من البوابة",
                txn.buyer_id,
            )

        # تحديث رصيد البائع (يستلم المبلغ)
        try:
            new_seller_balance = await self.wallets.deposit(
                txn.seller_id, txn.amount, txn.transaction_id,
            )
            txn.seller_balance_after = new_seller_balance
        except Exception as e:
            logger.error("خطأ في إيداع المبلغ للبائع: %s", e)

        # نقاط الولاء
        loyalty_points = int(paid_amount * self._loyalty_rate)
        if loyalty_points > 0:
            # تحديث نقاط الولاء في جدول المستثمر
            from sqlalchemy import select, update
            from core.account.models import Investor
            stmt = (
                update(Investor)
                .where(Investor.user_id == txn.buyer_id)
                .values(
                    loyalty_points=Investor.loyalty_points + loyalty_points,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self.session.execute(stmt)

            # حفظ في metadata
            meta = {}
            if txn.metadata_json:
                try:
                    meta = json.loads(txn.metadata_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            meta["loyalty_points_earned"] = loyalty_points
            txn.metadata_json = json.dumps(meta, ensure_ascii=False)

            logger.info(
                "نقاط الولاء: %d نقطة للمشتري %s",
                loyalty_points, txn.buyer_id,
            )

        return loyalty_points

    async def _process_refund(
        self,
        txn: PaymentTransaction,
        refund_amount: float,
        status: str,
    ) -> None:
        """معالجة الاسترداد — تحديث الأرصدة في DB."""
        # إرجاع المبلغ للمشتري
        try:
            new_buyer = await self.wallets.deposit(
                txn.buyer_id, refund_amount, f"{txn.transaction_id}-refund",
            )
            txn.buyer_balance_after = new_buyer
        except Exception as e:
            logger.error("خطأ في إيداع الاسترداد: %s", e)

        # خصم المبلغ من البائع
        try:
            new_seller = await self.wallets.withdraw(
                txn.seller_id, refund_amount, f"{txn.transaction_id}-refund",
            )
            txn.seller_balance_after = new_seller
        except (ValueError, Exception) as e:
            logger.error("خطأ في خصم الاسترداد من البائع: %s", e)

        txn.refunded_amount += refund_amount

        # تحديث مراجع الاسترداد
        refund_refs = []
        if txn.refund_refs_json:
            try:
                refund_refs = json.loads(txn.refund_refs_json)
            except (json.JSONDecodeError, TypeError):
                pass
        refund_refs.append(f"refund-{refund_amount}")
        txn.refund_refs_json = json.dumps(refund_refs)

        logger.info(
            "استرداد %.2f للمعاملة %s — إجمالي مسترد: %.2f",
            refund_amount, txn.transaction_id, txn.refunded_amount,
        )