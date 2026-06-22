"""data.land_database — facade re-exporting the in-memory land catalog + USAGE_COLORS."""

from models.land import USAGE_COLORS  # noqa: F401
from api.routes.account_store import lands_catalog_global  # noqa: F401
from core.domain import get_all_lands  # noqa: F401


def get_land(land_id: str):
    return lands_catalog_global.get(land_id)


__all__ = ["lands_catalog_global", "get_all_lands", "get_land", "USAGE_COLORS"]
