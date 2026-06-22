"""payment.idempotency_provider — facade stub for idempotency tracking.

Provides an IdempotencyProvider class compatible with the
signature expected by core.account.transaction_service:
    IdempotencyProvider(session)
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class IdempotencyProvider:
    """Tracks idempotency keys to prevent duplicate operations."""

    def __init__(self, session=None):
        self.session = session
        self._seen: Dict[str, Dict[str, Any]] = {}

    async def check_and_reserve(self, key: str, payload: Optional[dict] = None) -> bool:
        """Reserve an idempotency key. Returns False if already seen."""
        if key in self._seen:
            return False
        self._seen[key] = payload or {}
        return True

    async def release(self, key: str) -> None:
        """Release a previously reserved key (on failure)."""
        self._seen.pop(key, None)

    async def complete(self, key: str, result: Dict[str, Any]) -> None:
        """Mark a key as completed with the given result."""
        self._seen[key] = {"completed": True, "result": result}

    async def get_result(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the cached result for a completed key, or None."""
        entry = self._seen.get(key)
        if entry and entry.get("completed"):
            return entry.get("result")
        return None


__all__ = ["IdempotencyProvider"]
