"""
مدير الاسترداد — RefundManager (Async + PostgreSQL)
========================================================
استرداد مبلغ من معاملة مكتملة + استعلامات.

كل العمليات async وتستخدم PostgreSQL.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from payment.models import PaymentTransaction
from payment.transaction_store import TransactionStore
from payment.wallet_store import WalletStore
from payment.webhook_handler import WebhookHandler
from sqlalchemy.ext.asyncio import AsyncSession

from core.financial.base import (
    PaymentRouter,
    RefundRequest,
    RefundResult,
    TransactionStatus,
)

logger = logging.getLogger(__name__)


class RefundManager:
    """
    مدير الاسترداد — ينفذ الاسترداد اليدوي ويوفر استعلامات.

    كل العمليات async.
    """

    def __init__(
        self,
        session: AsyncSession,
        router: PaymentRouter,
        wallets: WalletStore,
        transactions: TransactionStore,
        webhook_handler: WebhookHandler,
    ):
        self.session = session
        self.router = router
        self.wallets = wallets
        self.transactions = transactions
        self.webhook_handler = webhook_handler

    async def refund_transaction(
        self,
        transaction_id: str,
        amount: Optional[float] = None,
        reason: str = "",
    ) -> RefundResult:
        """
        استرداد مبلغ من معاملة مكتملة (async).

        Args:
            transaction_id: معرف المعاملة
            amount: المبلغ (None = كامل المبلغ)
            reason: سبب الاسترداد
        """
        txn = await self.transactions.get(transaction_id)
        if not txn:
            raise ValueError(f"المعاملة {transaction_id} غير موجودة")

        if txn.status != TransactionStatus.COMPLETED:
            raise ValueError(
                f"لا يمكن استرداد معاملة بحالة: {txn.status} "
                "(يجب أن تكون مكتملة)"
            )

        refund_amount = amount or txn.amount

        if refund_amount > (txn.amount - txn.refunded_amount):
            raise ValueError(
                f"مبلغ الاسترداد ({refund_amount}) أكبر من المتبقي "
                f"({txn.amount - txn.refunded_amount})"
            )

        # تنفيذ الاسترداد في البوابة
        refund_request = RefundRequest(
            merchant_ref=transaction_id,
            amount=refund_amount,
            reason=reason,
            gateway_ref=txn.gateway_ref or "",
        )

        result = self.router.refund(txn.gateway_type, refund_request)

        if result.success:
            # تحديث سجل المعاملة في DB
            is_full = (refund_amount >= txn.amount - txn.refunded_amount)
            new_status = (
                TransactionStatus.REFUNDED if is_full
                else TransactionStatus.PARTIALLY_REFUNDED
            )

            # تحديث مراجع الاسترداد
            refund_refs = []
            if txn.refund_refs_json:
                try:
                    refund_refs = json.loads(txn.refund_refs_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            refund_refs.append(result.refund_ref)

            # تحديث مباشر في DB
            from datetime import datetime, timezone

            from sqlalchemy import update
            stmt = (
                update(PaymentTransaction)
                .where(PaymentTransaction.transaction_id == transaction_id)
                .values(
                    status=new_status.value,
                    refunded_amount=txn.refunded_amount + refund_amount,
                    refund_refs_json=json.dumps(refund_refs),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self.session.execute(stmt)

            # تحديث الأرصدة
            await self.webhook_handler._process_refund(
                txn, refund_amount, new_status.value,
            )

        return result

    # ──────────────────────────────────────────────────────────
    # استعلامات
    # ──────────────────────────────────────────────────────────

    async def get_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع معاملة بتفاصيلها."""
        txn = await self.transactions.get(transaction_id)
        if txn:
            return txn.to_dict()
        return None

    async def get_buyer_transactions(self, buyer_id: str) -> List[Dict[str, Any]]:
        """جميع معاملات مشترٍ."""
        txns = await self.transactions.get_by_buyer(buyer_id)
        return [t.to_dict() for t in txns]

    async def get_land_transactions(self, land_id: str) -> List[Dict[str, Any]]:
        """جميع معاملات أرض."""
        txns = await self.transactions.get_by_land(land_id)
        return [t.to_dict() for t in txns]

    async def get_buyer_summary(self, buyer_id: str) -> Dict[str, Any]:
        """ملخص حساب المشتري — بالكامل من PostgreSQL."""
        txns = await self.transactions.get_by_buyer(buyer_id)

        total_spent = sum(t.amount for t in txns if t.status == "completed")
        total_refunded = sum(t.refunded_amount for t in txns)
        pending = sum(1 for t in txns if t.status == "pending")
        total_loyalty = sum(t.loyalty_points_earned for t in txns)

        wallet_balance = await self.wallets.get_balance(buyer_id)

        return {
            "buyer_id": buyer_id,
            "wallet_balance": wallet_balance,
            "total_transactions": len(txns),
            "completed_transactions": sum(1 for t in txns if t.status == "completed"),
            "pending_transactions": pending,
            "total_spent_egp": round(total_spent, 2),
            "total_refunded_egp": round(total_refunded, 2),
            "net_spent_egp": round(total_spent - total_refunded, 2),
            "loyalty_points": total_loyalty,
        }