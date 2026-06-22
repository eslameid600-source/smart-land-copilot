"""infrastructure.database.connection — facade re-exporting DB connection helpers.

Provides:
    - get_session (async generator yielding AsyncSession)
    - get_db (FastAPI dependency alias)
"""

from infrastructure.database import get_db, get_session  # noqa: F401

__all__ = ["get_session", "get_db"]
