"""
Pytest fixtures — test database, sample data, auth helpers.
Uses manual drop/recreate per test for reliable SQLite isolation.
"""

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)

from core.account.models import Base

# ──────────────────────────────────────────────
# Event loop
# ──────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ──────────────────────────────────────────────
# Database setup / teardown
# ──────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

async def _ensure_tables(engine) -> None:
    """Idempotently ensure all tables exist (create or recreate)."""
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a clean session for each test.
    Drops and recreates all tables to guarantee isolation.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    await _ensure_tables(engine)
    TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = TestSessionLocal()
    async with session:
        yield session
    await session.close()
    await engine.dispose()


BUYER_ID = "user-buyer-001"
SELLER_ID = "user-seller-001"
BROKER_ID = "user-broker-001"
LAND_ID = "LAND-GIZA-001"
LAND_ID_2 = "LAND-GIZA-002"