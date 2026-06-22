"""core.domain.land_database — facade re-exporting the in-memory land catalog."""

from api.routes.account_store import lands_catalog_global  # noqa: F401
from core.domain import get_all_lands  # noqa: F401

__all__ = ["lands_catalog_global", "get_all_lands"]
