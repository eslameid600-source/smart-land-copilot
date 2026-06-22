"""
Landowner Service — manages landowner profiles, earnings, and withdrawals.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from purchase_module.models import Land, LandownerProfile, Transaction
from purchase_module.schemas import (
    LandownerDashboardResponse,
    LandownerProfileResponse,
    TransactionResponse,
    WithdrawalRequest,
    WithdrawalResponse,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class LandownerService:
    """Business logic for landowner accounts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ──────────────────────────────────────────
    # Profile management
    # ──────────────────────────────────────────

    async def get_or_create(self, user_id: str) -> LandownerProfile:
        """Get existing profile or create a new one."""
        profile = await self.db.get(LandownerProfile, user_id)
        if profile is None:
            profile = LandownerProfile(user_id=user_id)
            self.db.add(profile)
            await self.db.flush()
            await self.db.refresh(profile)
        return profile

    async def get_profile(self, user_id: str) -> LandownerProfileResponse:
        """Return the landowner profile."""
        profile = await self.get_or_create(user_id)
        return LandownerProfileResponse.model_validate(profile)

    # ──────────────────────────────────────────
    # Earnings management
    # ──────────────────────────────────────────

    async def credit_earnings(
        self,
        seller_id: str,
        amount: Decimal,
        transaction_id: str,
    ) -> None:
        """
        Credit sale proceeds to the landowner's wallet.
        Called by PaymentService.confirm() on successful purchase.
        """
        if amount <= 0:
            raise ValueError("Credit amount must be positive")

        profile = await self.get_or_create(seller_id)
        profile.wallet_balance_egp += amount
        profile.total_earnings_egp += amount
        profile.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def debit_earnings(
        self, seller_id: str, amount: Decimal
    ) -> None:
        """Debit from wallet (internal, called during refunds)."""
        if amount <= 0:
            raise ValueError("Debit amount must be positive")
        profile = await self.get_or_create(seller_id)
        if profile.wallet_balance_egp < amount:
            raise ValueError(
                f"Insufficient wallet: {profile.wallet_balance_egp} < {amount}"
            )
        profile.wallet_balance_egp -= amount
        profile.total_earnings_egp -= amount
        profile.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

    # ──────────────────────────────────────────
    # Withdrawals
    # ──────────────────────────────────────────

    async def withdraw(
        self, user_id: str, request: WithdrawalRequest
    ) -> WithdrawalResponse:
        """
        Process a withdrawal request from the landowner's wallet.
        Validates balance, updates withdrawal method, and deducts.
        """
        profile = await self.get_or_create(user_id)

        if profile.wallet_balance_egp < request.amount_egp:
            raise ValueError(
                f"Insufficient balance: {profile.wallet_balance_egp} EGP"
            )

        # Update withdrawal method
        profile.withdrawal_method = request.withdrawal_method.value
        if request.bank_account_ref:
            profile.bank_account_ref = request.bank_account_ref

        # Deduct
        profile.wallet_balance_egp -= request.amount_egp
        profile.total_withdrawn_egp += request.amount_egp
        profile.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(profile)

        return WithdrawalResponse(
            amount_withdrawn_egp=request.amount_egp,
            remaining_balance_egp=profile.wallet_balance_egp,
            withdrawal_method=request.withdrawal_method.value,
            status="processing",
        )

    # ──────────────────────────────────────────
    # Dashboard
    # ──────────────────────────────────────────

    async def get_dashboard(self, user_id: str) -> LandownerDashboardResponse:
        """Full landowner dashboard: profile, listed lands, sales report."""
        profile = await self.get_or_create(user_id)

        # Listed lands
        lands_q = select(Land).where(Land.owner_id == user_id)
        lands_result = await self.db.execute(lands_q)
        listed_lands = [
            {
                "land_id": land.land_id,
                "governorate": land.governorate,
                "region_city": land.region_city,
                "area_sqm": land.total_area_sqm,
                "price_per_sqm": float(land.price_per_sqm_egp),
                "total_price": float(land.price_per_sqm_egp * land.total_area_sqm),
                "status": land.status,
            }
            for land in lands_result.scalars().all()
        ]

        # Sales report from completed transactions
        sales_q = (
            select(Transaction)
            .where(
                Transaction.seller_id == user_id,
                Transaction.status == "completed",
            )
            .order_by(Transaction.completed_at.desc())
        )
        sales_result = await self.db.execute(sales_q)
        sales_txns = sales_result.scalars().all()

        total_sales = sum(t.amount_egp for t in sales_txns)
        total_fees = sum(t.platform_fee_egp for t in sales_txns)
        total_taxes = sum(t.tax_amount_egp for t in sales_txns)

        sales_report = {
            "completed_sales_count": len(sales_txns),
            "total_sales_egp": float(total_sales),
            "total_platform_fees_egp": float(total_fees),
            "total_taxes_egp": float(total_taxes),
            "net_earnings_egp": float(total_sales - total_fees - total_taxes),
            "recent_sales": [
                TransactionResponse.model_validate(tx) for tx in sales_txns[:10]
            ],
        }

        return LandownerDashboardResponse(
            profile=LandownerProfileResponse.model_validate(profile),
            listed_lands=listed_lands,
            sales_report=sales_report,
        )