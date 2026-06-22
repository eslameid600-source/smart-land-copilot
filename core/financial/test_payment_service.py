"""
Tests for PaymentService — initiate, confirm, refund, history.
"""

from decimal import Decimal

import pytest
from purchase_module.models import Land, Transaction
from purchase_module.schemas import PaymentMethod, TransactionCreate, TransactionStatus
from purchase_module.services.payment_service import PaymentService
from purchase_module.tests.conftest import BUYER_ID, LAND_ID, LAND_ID_2, SELLER_ID

# ══════════════════════════════════════════════
# INITIATE
# ══════════════════════════════════════════════

class TestInitiatePayment:
    """Tests for PaymentService.initiate()."""

    @pytest.mark.asyncio
    async def test_initiate_wallet_payment_succeeds(self, all_fixtures):
        """Wallet payment creates a pending transaction without calling a gateway."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("500000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        result = await svc.initiate(data)

        assert result.status == TransactionStatus.PENDING
        assert result.amount_egp == Decimal("500000.00")
        assert result.payment_method == PaymentMethod.WALLET
        assert result.transaction_id
        assert result.payment_url is None  # wallet has no redirect

        # Verify fees
        expected_fee = Decimal("500000.00") * Decimal("0.015")
        assert abs(result.platform_fee_egp - expected_fee) < Decimal("0.01")

        expected_tax = Decimal("500000.00") * Decimal("0.025")
        assert abs(result.tax_amount_egp - expected_tax) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_initiate_stores_transaction_in_db(self, all_fixtures):
        """The transaction is persisted to the database."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("200000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        result = await svc.initiate(data)

        tx = await db.get(Transaction, result.transaction_id)
        assert tx is not None
        assert tx.status == "pending"
        assert tx.buyer_id == BUYER_ID
        assert tx.seller_id == SELLER_ID

    @pytest.mark.asyncio
    async def test_initiate_land_not_found(self, db):
        """Raises ValueError if land does not exist."""
        data = TransactionCreate(
            land_id="NONEXISTENT",
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        with pytest.raises(ValueError, match="not found"):
            await svc.initiate(data)

    @pytest.mark.asyncio
    async def test_initiate_land_already_sold(self, db, sample_sold_land):
        """Raises ValueError if land is already sold."""
        data = TransactionCreate(
            land_id=LAND_ID_2,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        with pytest.raises(ValueError, match="already sold"):
            await svc.initiate(data)

    @pytest.mark.asyncio
    async def test_initiate_seller_mismatch(self, db, sample_land):
        """Raises ValueError if seller_id doesn't match land owner."""
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id="WRONG-SELLER",
            amount_egp=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        with pytest.raises(ValueError, match="does not match"):
            await svc.initiate(data)

    @pytest.mark.asyncio
    async def test_initiate_with_incentive_discount(self, all_fixtures):
        """Discount reduces net_amount but not amount_egp."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("500000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        result = await svc.initiate(data, incentive_discount=Decimal("5000.00"))

        assert result.amount_egp == Decimal("500000.00")
        assert result.discount_applied_egp == Decimal("5000.00")
        # Net should be amount - fee - tax - discount
        fee = Decimal("7500.00")    # 1.5%
        tax = Decimal("12500.00")   # 2.5%
        disc = Decimal("5000.00")
        expected_net = Decimal("500000.00") - fee - tax - disc
        assert abs(result.net_amount_egp - expected_net) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_initiate_discount_capped_at_10_percent(self, all_fixtures):
        """Total discount cannot exceed 10% of the amount."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        # Request a 20% discount — should be capped to 10%
        result = await svc.initiate(data, incentive_discount=Decimal("20000.00"))

        max_discount = Decimal("100000.00") * Decimal("0.10")
        assert result.discount_applied_egp <= max_discount + Decimal("0.01")


# ══════════════════════════════════════════════
# CONFIRM
# ══════════════════════════════════════════════

class TestConfirmPayment:
    """Tests for PaymentService.confirm()."""

    @pytest.mark.asyncio
    async def test_confirm_success_marks_completed(self, all_fixtures):
        """Successful confirmation marks transaction as completed."""
        db = all_fixtures["db"]
        # First initiate
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("500000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        initiated = await svc.initiate(data)

        # Confirm
        confirmed = await svc.confirm(
            transaction_id=initiated.transaction_id,
            gateway_ref="wallet-pay-001",
            success=True,
        )
        assert confirmed.status == TransactionStatus.COMPLETED
        assert confirmed.completed_at is not None

    @pytest.mark.asyncio
    async def test_confirm_success_marks_land_sold(self, all_fixtures):
        """Land status changes to Sold on successful confirmation."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("500000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        initiated = await svc.initiate(data)
        await svc.confirm(
            transaction_id=initiated.transaction_id,
            gateway_ref="wallet-001",
            success=True,
        )

        land = await db.get(Land, LAND_ID)
        assert land.status == "Sold"

    @pytest.mark.asyncio
    async def test_confirm_success_credits_seller_wallet(self, all_fixtures):
        """Seller wallet receives net amount on successful confirmation."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("500000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        initiated = await svc.initiate(data)

        # Get seller balance before confirm (bypass identity map)
        from purchase_module.models import LandownerProfile
        from sqlalchemy import select
        result = await db.execute(
            select(LandownerProfile).where(LandownerProfile.user_id == SELLER_ID)
        )
        seller_before = result.scalar_one()
        assert seller_before is not None, "Seller profile should exist"

        await svc.confirm(
            transaction_id=initiated.transaction_id,
            gateway_ref="wallet-001",
            success=True,
        )

        # Re-query seller after confirm (bypass identity map)
        result2 = await db.execute(
            select(LandownerProfile).where(LandownerProfile.user_id == SELLER_ID)
        )
        seller_after = result2.scalar_one()
        assert seller_after.wallet_balance_egp > seller_before.wallet_balance_egp
        assert seller_after.total_earnings_egp > seller_before.total_earnings_egp

    @pytest.mark.asyncio
    async def test_confirm_success_awards_loyalty_points(self, all_fixtures):
        """Buyer earns loyalty points on successful purchase."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("500000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        initiated = await svc.initiate(data)

        # Get buyer balance before confirm (bypass identity map)
        from purchase_module.models import InvestorProfile
        from sqlalchemy import select
        result = await db.execute(
            select(InvestorProfile).where(InvestorProfile.user_id == BUYER_ID)
        )
        buyer_before = result.scalar_one()
        assert buyer_before is not None

        await svc.confirm(
            transaction_id=initiated.transaction_id,
            gateway_ref="wallet-001",
            success=True,
        )

        # Re-query buyer after confirm
        result2 = await db.execute(
            select(InvestorProfile).where(InvestorProfile.user_id == BUYER_ID)
        )
        buyer_after = result2.scalar_one()
        assert buyer_after.loyalty_points > buyer_before.loyalty_points
        assert buyer_after.successful_purchases > buyer_before.successful_purchases

    @pytest.mark.asyncio
    async def test_confirm_failure_marks_failed(self, all_fixtures):
        """Failed confirmation marks transaction as failed."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        initiated = await svc.initiate(data)

        result = await svc.confirm(
            transaction_id=initiated.transaction_id,
            gateway_ref="fail-ref",
            success=False,
            gateway_message="Insufficient funds",
        )
        assert result.status == TransactionStatus.FAILED

        # Land should remain Available
        land = await db.get(Land, LAND_ID)
        assert land.status == "Available"

    @pytest.mark.asyncio
    async def test_confirm_nonexistent_transaction(self, db):
        """Raises ValueError for unknown transaction ID."""
        svc = PaymentService(db)
        with pytest.raises(ValueError, match="not found"):
            await svc.confirm("nonexistent-id", "ref", True)

    @pytest.mark.asyncio
    async def test_confirm_already_completed_fails(self, all_fixtures):
        """Cannot confirm a transaction that is already completed."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        initiated = await svc.initiate(data)
        await svc.confirm(initiated.transaction_id, "ref", True)

        with pytest.raises(ValueError, match="Cannot confirm"):
            await svc.confirm(initiated.transaction_id, "ref", True)


# ══════════════════════════════════════════════
# HISTORY
# ══════════════════════════════════════════════

class TestTransactionHistory:
    """Tests for PaymentService.get_history()."""

    @pytest.mark.asyncio
    async def test_history_returns_buyer_transactions(self, all_fixtures):
        """Buyer sees their own transactions in history."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        await svc.initiate(data)

        history = await svc.get_history(BUYER_ID)
        assert history.total >= 1
        assert len(history.transactions) >= 1
        assert history.transactions[0].buyer_id == BUYER_ID

    @pytest.mark.asyncio
    async def test_history_seller_sees_same_tx(self, all_fixtures):
        """Seller also sees the transaction in their history."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        await svc.initiate(data)

        history = await svc.get_history(SELLER_ID)
        assert history.total >= 1

    @pytest.mark.asyncio
    async def test_history_pagination(self, all_fixtures):
        """Pagination parameters are respected."""
        db = all_fixtures["db"]
        svc = PaymentService(db)
        # Create a few transactions
        for i in range(3):
            data = TransactionCreate(
                land_id=LAND_ID,
                buyer_id=BUYER_ID,
                seller_id=SELLER_ID,
                amount_egp=Decimal("100000.00"),
                payment_method=PaymentMethod.WALLET,
            )
            await svc.initiate(data)

        page1 = await svc.get_history(BUYER_ID, page=1, per_page=2)
        assert len(page1.transactions) <= 2
        assert page1.total >= 3

    @pytest.mark.asyncio
    async def test_history_filter_by_status(self, all_fixtures):
        """Can filter history by status."""
        db = all_fixtures["db"]
        data = TransactionCreate(
            land_id=LAND_ID,
            buyer_id=BUYER_ID,
            seller_id=SELLER_ID,
            amount_egp=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        svc = PaymentService(db)
        await svc.initiate(data)

        pending = await svc.get_history(BUYER_ID, status_filter="pending")
        assert all(t.status == TransactionStatus.PENDING for t in pending.transactions)

        completed = await svc.get_history(BUYER_ID, status_filter="completed")
        assert completed.total == 0