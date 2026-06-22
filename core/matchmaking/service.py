"""core.matchmaking.service — facade stub for matching investors to lands."""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MatchmakingService:
    """Stub matchmaking service."""

    async def match(self, investor_id: str, lands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Stub: returns the lands unchanged."""
        logger.info("Matchmaking stub: investor=%s lands=%d", investor_id, len(lands))
        return lands


matchmaking_service = MatchmakingService()

__all__ = ["MatchmakingService", "matchmaking_service"]
