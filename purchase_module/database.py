"""purchase_module.database — facade re-exporting DB init from core.account.models.

Also exposes a `get_db` FastAPI dependency that aliases the one from
infrastructure.database (which is the canonical place).
"""

from core.account.models import Base  # noqa: F401
from infrastructure.database import get_db, get_session  # noqa: F401


async def init_db(engine=None) -> None:
    """Initialize the database schema (stub)."""
    if engine is None:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


__all__ = ["Base", "init_db", "get_session", "get_db"]
