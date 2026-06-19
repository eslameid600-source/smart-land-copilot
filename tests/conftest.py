"""
Pytest fixtures — test database, sample data, auth helpers.
Uses manual drop/recreate per test for reliable SQLite isolation.
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from purchase_module.database import Base, test_engine
from purchase_module.models import (
    Land, Transaction, InvestorProfile, LandownerProfile, LoyaltyPointsLog,
)
from purchase_module.auth import create_access_token
from purchase_module.schemas import TransactionCreate, PaymentMethod


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

async def _ensure_tables() -> None:
    """Idempotently ensure all tables exist (create or recreate)."""
    async with test_engine.begin() as conn:
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
    await _ensure_tables()
    session = TestSessionLocal()
    async with session:
        yield session
    await session.close()


BUYER_ID = "user-buyer-001"
SELLER_ID = "user-seller-001"
BROKER_ID = "user-broker-001"
LAND_ID = "LAND-GIZA-001"
LAND_ID_2 = "LAND-GIZA-002"


@pytest_asyncio
async def sample_land(db: AsyncSession) -> Land:
    land = Land(
        land_id=LAND_ID, owner_id=SELLER_ID,
        governorate="القاهرة",
        region_city="القاهرة الجديدة",
        total_area_sqm=1000, price_per_sqm_egp=Decimal("500.00"),
        status="Available",
    )
    db.add(land)
    await db.flush()
    return land


@pytest_asyncio
async def sample_sold_land(db: AsyncSession) -> Land:
    land = Land(
        land_id=LAND_ID_2, owner_id=SELLER_ID,
        governorate="الجيزة",
        region_city="الشيخ زايد",
        total_area_sqm=500, price_per_sqm_egp=Decimal("300.00"), status="Sold",
    )
    db.add(land)
    await db.flush()
    return land


@pytest_asyncio
async def sample_buyer_profile(db: AsyncSession) -> InvestorProfile:
    profile = InvestorProfile(
        user_id=BUYER_ID, wallet_balance_egp=Decimal("10000.00"),
        loyalty_points=15, total_invested_egp=Decimal("0"),
        total_purchases=3, successful_purchases=3,
        registration_discount_pct=Decimal("0"),
    )
    db.add(profile)
    await db.flush()
    return profile


@pytest_asyncio
async def sample_seller_profile(db: AsyncSession) -> LandownerProfile:
    profile = LandownerProfile(
        user_id=SELLER_ID, wallet_balance_egp=Decimal("5000.00"),
        total_earnings_egp=Decimal("20000.00"),
        total_withdrawn_egp=Decimal("5000.00"),
        lands_for_sale=2, lands_sold=1,
        withdrawal_method="bank_transfer",
        bank_account_ref="EG-001234567890",
    )
    db.add(profile)
    await db.flush()
    return profile


@pytest_asyncio
async def all_fixtures(
    db, sample_land, sample_buyer_profile, sample_seller_profile
):
    return {
        "db": db,
        "land": sample_land,
        "buyer": sample_buyer_profile,
        "seller": sample_seller_profile,
    }


@pytest.fixture
def buyer_token() -> str:
    return create_access_token(BUYER_ID, role="Buyer/Investor")


@pytest.fixture
def seller_token() -> str:
    return create_access_token(SELLER_ID, role="Seller/Owner")


@pytest.fixture
def buyer_auth_headers(buyer_token) -> dict:
    return {"Authorization": f"Bearer {buyer_token}"}


@pytest.fixture
def seller_auth_headers(seller_token) -> dict:
    return {"Authorization": f"Bearer {seller_token}"}


@pytest.fixture
def sample_tx_create() -> TransactionCreate:
    return TransactionCreate(
        land_id=LAND_ID, buyer_id=BUYER_ID, seller_id=SELLER_ID,
        amount_egp=Decimal("500000.00"),
        payment_method=PaymentMethod.WALLET, apply_loyalty=False,
    )
CONFT_EOF