"""payment.refund_manager — facade stub for handling refunds."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RefundManager:
    """Stub refund manager — wire to real gateway in production."""

    def __init__(self, session=None, router=None, wallets=None, transactions=None, webhook_handler=None):
        self.session = session
        self.router = router
        self.wallets = wallets
        self.transactions = transactions
        self.webhook_handler = webhook_handler

    async def refund_transaction(self, payment_id: str, amount: Optional[float] = None, reason: str = "") -> Dict[str, Any]:
        logger.info("RefundManager stub: payment_id=%s amount=%s reason=%s", payment_id, amount, reason)
        return {"payment_id": payment_id, "status": "refunded", "amount_egp": amount or 0, "reason": reason}

    async def get_transaction(self, payment_id: str) -> Optional[Dict[str, Any]]:
        return None

    async def get_buyer_transactions(self, buyer_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return []

    async def get_land_transactions(self, land_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return []

    async def get_buyer_summary(self, buyer_id: str) -> Dict[str, Any]:
        return {"buyer_id": buyer_id, "total_spent_egp": 0.0, "total_transactions": 0}


__all__ = ["RefundManager"]
