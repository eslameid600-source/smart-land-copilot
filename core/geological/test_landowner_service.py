"""
Tests for LandownerService — profile, earnings, withdrawal, dashboard.
"""

import pytest
from decimal import Decimal

from purchase_module.models import LandownerProfile, Land
from purchase_module.services.landowner_service import LandownerService
from purchase_module.schemas import (
    WithdrawalRequest,
    WithdrawalMethod,
)
from purchase_module.tests.conftest import BUYER_ID, SELLER_ID, LAND_ID


# ══════════════════════════════════════════════
# PROFILE
# ══════════════════════════════════════════════

class TestLandownerProfile:
    @pytest.mark.asyncio
    async def test_get_or_create_new(self, db):
        svc = LandownerService(db)
        profile = await svc.get_or_create("new-landowner-001")
        assert profile.user_id == "new-landowner-001"
        assert profile.wallet_balance_egp == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_profile_returns_schema(self, all_fixtures):
        db = all_fixtures["db"]
        svc = LandownerService(db)
        response = await svc.get_profile(SELLER_ID)
        assert response.user_id == SELLER_ID
        assert response.total_earnings_egp == Decimal("20000.00")
        assert response.lands_sold == 1


# ══════════════════════════════════════════════
# EARNINGS
# ══════════════════════════════════════════════

class TestEarnings:
    @pytest.mark.asyncio
    async def test_credit_earnings(self, all_fixtures):
        """Crediting increases wallet and total earnings."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        await svc.credit_earnings(
            seller_id=SELLER_ID,
            amount=Decimal("50000.00"),
            transaction_id="tx-earn-001",
        )
        profile = await db.get(LandownerProfile, SELLER_ID)
        assert profile.wallet_balance_egp == Decimal("55000.00")
        assert profile.total_earnings_egp == Decimal("70000.00")

    @pytest.mark.asyncio
    async def test_debit_earnings(self, all_fixtures):
        """Debiting decreases wallet and total earnings."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        await svc.debit_earnings(seller_id=SELLER_ID, amount=Decimal("2000.00"))
        profile = await db.get(LandownerProfile, SELLER_ID)
        assert profile.wallet_balance_egp == Decimal("3000.00")
        assert profile.total_earnings_egp == Decimal("18000.00")

    @pytest.mark.asyncio
    async def test_debit_insufficient_raises(self, all_fixtures):
        """Cannot debit more than wallet balance."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        with pytest.raises(ValueError, match="Insufficient"):
            await svc.debit_earnings(SELLER_ID, Decimal("99999.00"))

    @pytest.mark.asyncio
    async def test_credit_zero_raises(self, all_fixtures):
        """Cannot credit zero or negative amount."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        with pytest.raises(ValueError, match="positive"):
            await svc.credit_earnings(
                seller_id=SELLER_ID,
                amount=Decimal("0"),
                transaction_id="tx-test-zero",
            )


# ══════════════════════════════════════════════
# WITHDRAWAL
# ══════════════════════════════════════════════

class TestWithdrawal:
    @pytest.mark.asyncio
    async def test_withdraw_success(self, all_fixtures):
        """Successful withdrawal reduces wallet and increases withdrawn total."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        request = WithdrawalRequest(
            amount_egp=Decimal("3000.00"),
            withdrawal_method=WithdrawalMethod.BANK_TRANSFER,
            bank_account_ref="EG-NEW-001",
        )
        result = await svc.withdraw(SELLER_ID, request)
        assert result.amount_withdrawn_egp == Decimal("3000.00")
        assert result.remaining_balance_egp == Decimal("2000.00")
        assert result.status == "processing"
        assert result.withdrawal_method == "bank_transfer"

    @pytest.mark.asyncio
    async def test_withdraw_updates_method(self, all_fixtures):
        """Withdrawal method is saved to profile."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        request = WithdrawalRequest(
            amount_egp=Decimal("1000.00"),
            withdrawal_method=WithdrawalMethod.FAWRY,
        )
        await svc.withdraw(SELLER_ID, request)

        profile = await db.get(LandownerProfile, SELLER_ID)
        assert profile.withdrawal_method == "fawry"

    @pytest.mark.asyncio
    async def test_withdraw_insufficient_raises(self, all_fixtures):
        """Cannot withdraw more than wallet balance."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        request = WithdrawalRequest(
            amount_egp=Decimal("99999.00"),
            withdrawal_method=WithdrawalMethod.CHECK,
        )
        with pytest.raises(ValueError, match="Insufficient"):
            await svc.withdraw(SELLER_ID, request)

    @pytest.mark.asyncio
    async def test_withdraw_bank_requires_ref(self, all_fixtures):
        """Bank transfer requires bank_account_ref."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        request = WithdrawalRequest(
            amount_egp=Decimal("1000.00"),
            withdrawal_method=WithdrawalMethod.BANK_TRANSFER,
            # bank_account_ref intentionally omitted
        )
        # Pydantic validation should catch this
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="bank_account_ref"):
            WithdrawalRequest(
                amount_egp=Decimal("1000.00"),
                withdrawal_method=WithdrawalMethod.BANK_TRANSFER,
                bank_account_ref=None,
            )


# ══════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════

class TestDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_returns_profile_and_lands(self, all_fixtures):
        """Dashboard includes profile and listed lands."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        dashboard = await svc.get_dashboard(SELLER_ID)
        assert dashboard.profile.user_id == SELLER_ID
        assert isinstance(dashboard.listed_lands, list)
        assert isinstance(dashboard.sales_report, dict)

    @pytest.mark.asyncio
    async def test_dashboard_sales_report(self, all_fixtures):
        """Sales report has correct structure."""
        db = all_fixtures["db"]
        svc = LandownerService(db)
        dashboard = await svc.get_dashboard(SELLER_ID)
        report = dashboard.sales_report
        assert "total_sales_egp" in report
        assert "net_earnings_egp" in report
        assert "completed_sales_count" in report
        assert "total_platform_fees_egp" in report
        assert "total_taxes_egp" in report