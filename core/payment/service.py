"""core.payment.service — facade stub for payment orchestration."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def process_payment(
    user_id: str,
    amount_egp: float,
    provider: str = "wallet",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Stub payment processor — wire to real gateway in production."""
    logger.info("Payment stub: user=%s amount=%.2f provider=%s", user_id, amount_egp, provider)
    return {
        "payment_id": f"pay-stub-{user_id}-{int(amount_egp)}",
        "status": "succeeded",
        "amount_egp": amount_egp,
        "provider": provider,
    }


async def refund_payment(payment_id: str, amount: Optional[float] = None) -> Dict[str, Any]:
    """Stub refund handler."""
    logger.info("Refund stub: payment_id=%s amount=%s", payment_id, amount)
    return {"payment_id": payment_id, "status": "refunded", "amount_egp": amount or 0}


__all__ = ["process_payment", "refund_payment"]
