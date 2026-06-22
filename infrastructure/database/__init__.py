"""infrastructure.database — facade re-exporting from core.account + api.routes.account_store."""

# Async DB session (placeholder if no real DB engine)
from sqlalchemy.ext.asyncio import AsyncSession

# Re-export models from the real location
from core.account.models import (  # noqa: F401
    Base,
    Investor,
    Landowner,
    OwnedLand,
    Broker,
    BrokerAssignment,
    BrokerTransaction,
    LandDocument,
    LandGPSLog,
    WalletTransaction,
    LandownerTransaction,
    Land,
    Transaction,
    InvestmentHistory,
    LandCommissionSettings,
    LoyaltyPointsLog,
    PaymentTransaction,
    User,
    UserRole,
    UserStatus,
)

# Re-export sync stores from account_store
from api.routes.account_store import (  # noqa: F401
    InvestorStore as _SyncInvestorStore,
    LandownerStore as _SyncLandownerStore,
    transfer_ownership as _sync_transfer_ownership,
    init_stores as _sync_init_stores,
)


class database:
    """Stub namespace — historically `infrastructure.database.database`."""

    @staticmethod
    def get_engine():
        raise NotImplementedError("Use real SQLAlchemy engine in production.")

    @staticmethod
    async def get_session() -> AsyncSession:
        raise NotImplementedError("Use real SQLAlchemy AsyncSession in production.")


# Common alias for `from infrastructure.database.database import get_db`
async def get_db():
    """FastAPI dependency — yields an AsyncSession (stub)."""
    raise NotImplementedError("Wire real engine in production.")


async def get_session() -> AsyncSession:
    """Yields an AsyncSession (stub)."""
    raise NotImplementedError("Wire real engine in production.")


# `connection` submodule facade
connection = type("connection", (), {"get_session": get_session, "get_db": get_db})
