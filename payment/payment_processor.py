"""payment.payment_processor — facade stub for the payment processor."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class PaymentProcessor:
    """Stub payment processor — wires together wallet/transaction stores.

    Real implementation should integrate with Fawry/Stripe/Paymob.
    """

    def __init__(self, session=None, router=None, wallets=None, transactions=None, idempotency=None):
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
        **kwargs,
    ) -> Dict[str, Any]:
        """Process a land-purchase transaction."""
        logger.info(
            "PaymentProcessor stub: land=%s buyer=%s seller=%s amount=%.2f",
            land_id, buyer_id, seller_id, amount,
        )
        return {
            "payment_id": f"pay-{land_id}-{buyer_id}",
            "status": "succeeded",
            "amount_egp": amount,
            "land_id": land_id,
            "buyer_id": buyer_id,
            "seller_id": seller_id,
        }


__all__ = ["PaymentProcessor"]
