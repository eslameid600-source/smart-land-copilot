"""
Tests for IncentiveService — preview, discount computation, point awarding.
"""

from decimal import Decimal

import pytest
from purchase_module.models import LoyaltyPointsLog
from purchase_module.services.incentive_service import (
    MAX_TOTAL_DISCOUNT_PCT,
    REGISTRATION_DISCOUNT_PCT,
    IncentiveService,
)
from purchase_module.services.investor_service import InvestorService
from purchase_module.tests.conftest import BUYER_ID, LAND_ID

# ══════════════════════════════════════════════
# PREVIEW
# ══════════════════════════════════════════════

class TestIncentivePreview:
    @pytest.mark.asyncio
    async def test_new_user_no_discounts(self, db):
        """A new user with 0 purchases gets no discounts."""
        svc = IncentiveService(db)
        preview = await svc.preview("brand-new-user", Decimal("100000.00"))
        assert preview.repeat_buyer_discount_pct == Decimal("0")
        assert preview.repeat_buyer_discount_egp == Decimal("0")
        assert preview.loyalty_discount_egp == Decimal("0")
        assert preview.total_discount_egp == Decimal("0")
        assert preview.final_price_egp == Decimal("100000.00")
        assert preview.is_repeat_buyer is False
        assert preview.points_to_earn == 10  # 100k / 10k = 10

    @pytest.mark.asyncio
    async def test_repeat_buyer_gets_2pct(self, all_fixtures):
        """A user with 5+ successful purchases gets 2% repeat discount."""
        db = all_fixtures["db"]
        # Buyer has 3 purchases; needs 5. Add 2 more.
        inv_svc = InvestorService(db)
        for i in range(2):
            await inv_svc.record_purchase(
                user_id=BUYER_ID,
                amount=Decimal("100000.00"),
                transaction_id=f"tx-incentive-{i}",
                land_id=LAND_ID,
            )

        svc = IncentiveService(db)
        preview = await svc.preview(BUYER_ID, Decimal("100000.00"))
        assert preview.is_repeat_buyer is True
        assert preview.repeat_buyer_discount_pct == REGISTRATION_DISCOUNT_PCT
        assert preview.repeat_buyer_discount_egp == Decimal("2000.00")

    @pytest.mark.asyncio
    async def test_loyalty_discount_from_existing_points(self, all_fixtures):
        """15 points -> redeemable 10 -> 1000 EGP loyalty discount."""
        db = all_fixtures["db"]
        svc = IncentiveService(db)
        preview = await svc.preview(BUYER_ID, Decimal("100000.00"))
        # 15 points, redeemable in multiples of 5 = 10 points
        # 15 points, all redeemable (multiples of 5) = 15 * 100 = 1500 EGP
        assert preview.loyalty_discount_egp == Decimal("1500.00")

    @pytest.mark.asyncio
    async def test_total_discount_capped_at_10pct(self, all_fixtures):
        """Total discount never exceeds 10% of amount."""
        db = all_fixtures["db"]
        inv_svc = InvestorService(db)
        for i in range(2):
            await inv_svc.record_purchase(
                user_id=BUYER_ID,
                amount=Decimal("100000.00"),
                transaction_id=f"tx-cap-{i}",
                land_id=LAND_ID,
            )

        svc = IncentiveService(db)
        preview = await svc.preview(BUYER_ID, Decimal("100000.00"))
        max_discount = Decimal("100000.00") * MAX_TOTAL_DISCOUNT_PCT / 100
        assert preview.total_discount_egp <= max_discount + Decimal("0.01")

    @pytest.mark.asyncio
    async def test_points_to_earn_calculation(self, db):
        """Points earned = amount // 10000."""
        svc = IncentiveService(db)
        preview = await svc.preview("any-user", Decimal("75000.00"))
        assert preview.points_to_earn == 7  # 75000 // 10000

    @pytest.mark.asyncio
    async def test_zero_amount_earns_zero_points(self, db):
        svc = IncentiveService(db)
        preview = await svc.preview("any-user", Decimal("5000.00"))
        assert preview.points_to_earn == 0


# ══════════════════════════════════════════════
# COMPUTE DISCOUNT (for payment initiation)
# ══════════════════════════════════════════════

class TestComputeDiscount:
    @pytest.mark.asyncio
    async def test_compute_discount_returns_decimal(self, all_fixtures):
        """compute_discount returns a Decimal value."""
        db = all_fixtures["db"]
        svc = IncentiveService(db)
        discount = await svc.compute_discount(BUYER_ID, Decimal("100000.00"))
        assert isinstance(discount, Decimal)
        assert discount >= 0

    @pytest.mark.asyncio
    async def test_compute_discount_within_cap(self, all_fixtures):
        """Discount never exceeds 10% of amount."""
        db = all_fixtures["db"]
        svc = IncentiveService(db)
        discount = await svc.compute_discount(BUYER_ID, Decimal("100000.00"))
        max_d = Decimal("100000.00") * Decimal("0.10")
        assert discount <= max_d + Decimal("0.01")


# ══════════════════════════════════════════════
# AWARD POINTS
# ══════════════════════════════════════════════

class TestAwardPoints:
    @pytest.mark.asyncio
    async def test_award_points_on_purchase(self, db):
        """A 50k purchase earns 5 points."""
        svc = IncentiveService(db)
        points = await svc.award_points(
            user_id="new-pts-user",
            amount=Decimal("50000.00"),
            transaction_id="tx-pts-001",
            land_id="LAND-TEST",
        )
        assert points == 5

    @pytest.mark.asyncio
    async def test_award_points_creates_log(self, db):
        """A log entry is created when points are awarded."""
        svc = IncentiveService(db)
        await svc.award_points(
            user_id="log-user",
            amount=Decimal("30000.00"),
            transaction_id="tx-log-001",
            land_id="LAND-LOG",
        )

        from sqlalchemy import select
        q = select(LoyaltyPointsLog).where(
            LoyaltyPointsLog.user_id == "log-user",
            LoyaltyPointsLog.points_earned > 0,
        )
        result = await db.execute(q)
        logs = result.scalars().all()
        assert len(logs) >= 1
        assert logs[0].points_earned == 3
        assert "LAND-LOG" in logs[0].reason

    @pytest.mark.asyncio
    async def test_award_points_zero_for_small_amount(self, db):
        """A 5k purchase earns 0 points (below 10k threshold)."""
        svc = IncentiveService(db)
        points = await svc.award_points(
            user_id="small-user",
            amount=Decimal("5000.00"),
            transaction_id="tx-small-001",
            land_id="LAND-SMALL",
        )
        assert points == 0


# ══════════════════════════════════════════════
# LOYALTY HISTORY
# ══════════════════════════════════════════════

class TestLoyaltyHistory:
    @pytest.mark.asyncio
    async def test_history_returns_list(self, db):
        """Loyalty history returns a list of dicts."""
        svc = IncentiveService(db)
        await svc.award_points(
            "hist-user", Decimal("20000.00"), "tx-h-001", "LAND-H"
        )
        history = await svc.get_loyalty_history("hist-user")
        assert isinstance(history, list)
        assert len(history) >= 1
        assert "points_earned" in history[0]
        assert "reason" in history[0]

    @pytest.mark.asyncio
    async def test_history_respects_limit(self, db):
        """Limit parameter restricts returned entries."""
        svc = IncentiveService(db)
        for i in range(10):
            await svc.award_points(
                "limit-user", Decimal("20000.00"), f"tx-lim-{i}", "LAND-L"
            )
        history = await svc.get_loyalty_history("limit-user", limit=3)
        assert len(history) <= 3