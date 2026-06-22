"""payment.webhook_handler — facade stub for incoming payment webhooks."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Stub webhook handler — wire to real gateway webhook flow in production."""

    def __init__(self, session=None, router=None, wallets=None, transactions=None):
        self.session = session
        self.router = router
        self.wallets = wallets
        self.transactions = transactions

    async def handle_webhook(self, gateway: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("WebhookHandler stub: gateway=%s keys=%s", gateway, list(payload.keys()))
        return {"status": "acknowledged", "gateway": gateway}


__all__ = ["WebhookHandler"]
