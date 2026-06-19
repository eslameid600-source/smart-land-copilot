"""
Tests for InvestorService — profile, wallet, loyalty, deposit.
"""

import pytest
from decimal import Decimal

from purchase_module.models import InvestorProfile, Land, Transaction
from purchase_module.services.investor_service import (
    InvestorService,
    REPEAT_BUYER_THRESHOLD,
    REGISTRATION_DISCOUNT_PCT,
)
from purchase_module.schemas import TransactionCreate, PaymentMethod
from purchase_module.tests.conftest import BUYER_ID, SELLER_ID, LAND_ID


# ══════════════════════════════════════════════
# PROFILE
# ══════════════════════════════════════════════

class TestInvestorProfile:
    @pytest.mark.asyncio
    async def test_get_or_create_creates_new(self, db):
        """A new profile is created for a user who doesn't have one."""
        svc = InvestorService(db)
        profile = await svc.get_or_create("new-user-123")
        assert profile.user_id == "new-user-123"
        assert profile.wallet_balance_egp == Decimal("0")
        assert profile.loyalty_points == 0
        assert profile.total_purchases == 0

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing(self, all_fixtures):
        """An existing profile is returned without creating a duplicate."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        profile = await svc.get_or_create(BUYER_ID)
        assert profile.wallet_balance_egp == Decimal("10000.00")

    @pytest.mark.asyncio
    async def test_get_profile_returns_schema(self, all_fixtures):
        """get_profile returns a valid Pydantic response."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        response = await svc.get_profile(BUYER_ID)
        assert response.user_id == BUYER_ID
        assert response.wallet_balance_egp == Decimal("10000.00")


# ══════════════════════════════════════════════
# WALLET
# ══════════════════════════════════════════════

class TestInvestorWallet:
    @pytest.mark.asyncio
    async def test_deposit_credits_balance(self, all_fixtures):
        """Depositing funds increases wallet balance."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        result = await svc.deposit_to_wallet(BUYER_ID, Decimal("5000.00"))
        assert result.wallet_balance_egp == Decimal("15000.00")

    @pytest.mark.asyncio
    async def test_deposit_zero_raises(self, all_fixtures):
        """Cannot deposit zero or negative amount."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        with pytest.raises(ValueError, match="positive"):
            await svc.deposit_to_wallet(BUYER_ID, Decimal("0"))

    @pytest.mark.asyncio
    async def test_deduct_reduces_balance(self, all_fixtures):
        """Deducting from wallet decreases balance."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        await svc.deduct_from_wallet(BUYER_ID, Decimal("3000.00"))
        profile = await db.get(InvestorProfile, BUYER_ID)
        assert profile.wallet_balance_egp == Decimal("7000.00")

    @pytest.mark.asyncio
    async def test_deduct_insufficient_raises(self, all_fixtures):
        """Cannot deduct more than available balance."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        with pytest.raises(ValueError, match="Insufficient"):
            await svc.deduct_from_wallet(BUYER_ID, Decimal("99999.00"))


# ══════════════════════════════════════════════
# WALLET DASHBOARD
# ══════════════════════════════════════════════

class TestWalletDashboard:
    @pytest.mark.asyncio
    async def test_wallet_view_includes_owned_lands(self, all_fixtures):
        """Dashboard returns list of owned lands (note: owned via transactions)."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        wallet = await svc.get_wallet_view(BUYER_ID)
        assert wallet.profile.user_id == BUYER_ID
        assert wallet.profile.wallet_balance_egp == Decimal("10000.00")
        assert "owned_lands" in wallet.model_dump()
        assert "recent_transactions" in wallet.model_dump()

    @pytest.mark.asyncio
    async def test_wallet_view_shows_loyalty_discount(self, all_fixtures):
        """Dashboard calculates available loyalty discount."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        wallet = await svc.get_wallet_view(BUYER_ID)
        # 15 points, redeemable in multiples of 5 = 10 points = 1000 EGP
        assert wallet.available_loyalty_discount_egp == Decimal("1500.00")


# ══════════════════════════════════════════════
# LOYALTY POINTS
# ══════════════════════════════════════════════

class TestLoyaltyPoints:
    @pytest.mark.asyncio
    async def test_redeem_points_success(self, all_fixtures):
        """Redeeming 5 points gives 500 EGP discount."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        result = await svc.redeem_loyalty_points(BUYER_ID, 5)
        assert result.points_redeemed == 5
        assert result.discount_egp == Decimal("500.00")
        assert result.remaining_points == 10

    @pytest.mark.asyncio
    async def test_redeem_less_than_minimum_raises(self, all_fixtures):
        """Cannot redeem fewer than 5 points."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        with pytest.raises(ValueError, match="5 points"):
            await svc.redeem_loyalty_points(BUYER_ID, 3)

    @pytest.mark.asyncio
    async def test_redeem_not_multiple_raises(self, all_fixtures):
        """Points must be in multiples of 5."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        with pytest.raises(ValueError, match="multiples"):
            await svc.redeem_loyalty_points(BUYER_ID, 7)

    @pytest.mark.asyncio
    async def test_redeem_insufficient_points(self, db):
        """Cannot redeem more points than available."""
        svc = InvestorService(db)
        profile = await svc.get_or_create("empty-user")
        with pytest.raises(ValueError, match="Insufficient"):
            await svc.redeem_loyalty_points("empty-user", 5)

    @pytest.mark.asyncio
    async def test_redeem_creates_log_entry(self, all_fixtures):
        """A LoyaltyPointsLog entry is created on redemption."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        await svc.redeem_loyalty_points(BUYER_ID, 5)

        from purchase_module.models import LoyaltyPointsLog
        from sqlalchemy import select
        q = select(LoyaltyPointsLog).where(
            LoyaltyPointsLog.user_id == BUYER_ID,
            LoyaltyPointsLog.points_used > 0,
        )
        result = await db.execute(q)
        logs = result.scalars().all()
        assert len(logs) >= 1
        assert logs[0].points_used == 5


# ══════════════════════════════════════════════
# RECORD PURCHASE (called by PaymentService)
# ══════════════════════════════════════════════

class TestRecordPurchase:
    @pytest.mark.asyncio
    async def test_record_increments_counters(self, all_fixtures):
        """Successful purchase increments purchase counters."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        # Record the purchase
        await svc.record_purchase(
            user_id=BUYER_ID,
            amount=Decimal("200000.00"),
            transaction_id="tx-test-001",
            land_id=LAND_ID,
        )

        after = await db.get(InvestorProfile, BUYER_ID)
        # Profile started with 3 purchases from fixture; should now be 4
        assert after.total_purchases == 4
        assert after.successful_purchases == 4
        assert after.total_invested_egp == Decimal("200000.00")

    @pytest.mark.asyncio
    async def test_record_awards_loyalty_points(self, all_fixtures):
        """A 200k purchase earns 20 loyalty points."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        await svc.record_purchase(
            user_id=BUYER_ID,
            amount=Decimal("200000.00"),
            transaction_id="tx-test-002",
            land_id=LAND_ID,
        )

        after = await db.get(InvestorProfile, BUYER_ID)
        # Profile started with 15 points from fixture; 200k/10k = 20 more
        assert after.loyalty_points == 35

    @pytest.mark.asyncio
    async def test_record_small_purchase_zero_points(self, all_fixtures):
        """A 5,000 EGP purchase earns 0 points (below 10k threshold)."""
        db = all_fixtures["db"]
        svc = InvestorService(db)
        before = await svc.get_or_create(BUYER_ID)

        await svc.record_purchase(
            user_id=BUYER_ID,
            amount=Decimal("5000.00"),
            transaction_id="tx-test-003",
            land_id=LAND_ID,
        )

        after = await db.get(InvestorProfile, BUYER_ID)
        assert after.loyalty_points == before.loyalty_points  # no change

    @pytest.mark.asyncio
    async def test_repeat_buyer_discount_unlocked(self, all_fixtures):
        """After 5 successful purchases, 2% discount is unlocked."""
        db = all_fixtures["db"]
        svc = InvestorService(db)

        # Buyer already has 3 purchases; add 2 more
        for i in range(2):
            await svc.record_purchase(
                user_id=BUYER_ID,
                amount=Decimal("50000.00"),
                transaction_id=f"tx-repeat-{i}",
                land_id=LAND_ID,
            )

        profile = await db.get(InvestorProfile, BUYER_ID)
        assert profile.successful_purchases >= REPEAT_BUYER_THRESHOLD
        assert profile.registration_discount_pct >= REGISTRATION_DISCOUNT_PCT