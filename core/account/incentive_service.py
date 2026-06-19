"""
Incentive Service — unified incentive calculation and management.
Coordinates between repeat-buyer discounts and loyalty point redemptions.
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from purchase_module.models import InvestorProfile, LoyaltyPointsLog
from purchase_module.schemas import IncentivePreviewResponse, LoyaltyRedeemResponse

logger = logging.getLogger(__name__)

# ── Constants (single source of truth) ──
REPEAT_BUYER_THRESHOLD = 5       # successful purchases to unlock discount
REGISTRATION_DISCOUNT_PCT = Decimal("2.0")  # 2% discount on registration fees
POINTS_PER_10K_EGP = 1           # 1 point per 10,000 EGP spent
POINTS_NEEDED_FOR_REDEEM = 5     # 5 points minimum
EGP_PER_POINT = Decimal("100")   # 100 EGP per point redeemed
MAX_TOTAL_DISCOUNT_PCT = Decimal("10.0")  # total discount cap


class IncentiveService:
    """
    Computes all available incentives for a given purchase amount
    and manages loyalty point lifecycle.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_profile(self, user_id: str) -> InvestorProfile:
        from purchase_module.services.investor_service import InvestorService
        svc = InvestorService(self.db)
        return await svc.get_or_create(user_id)

    # ──────────────────────────────────────────
    # Preview (read-only calculation)
    # ──────────────────────────────────────────

    async def preview(
        self, user_id: str, amount: Decimal
    ) -> IncentivePreviewResponse:
        """
        Calculate every available incentive for a purchase of `amount` EGP.
        This does NOT modify any state — it's for display before checkout.
        """
        profile = await self._get_profile(user_id)
        is_repeat = profile.successful_purchases >= REPEAT_BUYER_THRESHOLD

        # 1. Repeat-buyer discount (2% on registration fees)
        repeat_pct = REGISTRATION_DISCOUNT_PCT if is_repeat else Decimal("0")
        repeat_discount = (amount * repeat_pct / 100).quantize(Decimal("0.01"))

        # 2. Loyalty points discount
        redeemable_pts = (
            (profile.loyalty_points // POINTS_NEEDED_FOR_REDEEM)
            * POINTS_NEEDED_FOR_REDEEM
        )
        loyalty_discount = Decimal(redeemable_pts) * EGP_PER_POINT

        # 3. Cap at 10% total
        total_discount = repeat_discount + loyalty_discount
        max_discount = (amount * MAX_TOTAL_DISCOUNT_PCT / 100).quantize(
            Decimal("0.01")
        )
        if total_discount > max_discount and total_discount > 0:
            scale = max_discount / total_discount
            repeat_discount = (repeat_discount * scale).quantize(Decimal("0.01"))
            loyalty_discount = (loyalty_discount * scale).quantize(Decimal("0.01"))
            total_discount = max_discount

        points_to_earn = int(amount // 10_000)

        return IncentivePreviewResponse(
            repeat_buyer_discount_pct=repeat_pct,
            repeat_buyer_discount_egp=repeat_discount,
            loyalty_discount_egp=loyalty_discount,
            total_discount_egp=total_discount,
            points_to_earn=points_to_earn,
            final_price_egp=(amount - total_discount).quantize(Decimal("0.01")),
            is_repeat_buyer=is_repeat,
            available_loyalty_points=profile.loyalty_points,
        )

    # ──────────────────────────────────────────
    # Compute discount for payment initiation
    # ──────────────────────────────────────────

    async def compute_discount(
        self, user_id: str, amount: Decimal
    ) -> Decimal:
        """
        Compute the total discount EGP to apply during payment.
        Called by PaymentService.initiate().
        """
        preview = await self.preview(user_id, amount)
        return preview.total_discount_egp

    # ──────────────────────────────────────────
    # Loyalty point lifecycle
    # ──────────────────────────────────────────

    async def award_points(
        self,
        user_id: str,
        amount: Decimal,
        transaction_id: str,
        land_id: str,
    ) -> int:
        """
        Award loyalty points after a successful purchase.
        Returns the number of points earned.
        """
        points_earned = int(amount // 10_000)
        if points_earned <= 0:
            return 0

        profile = await self._get_profile(user_id)
        profile.loyalty_points += points_earned
        profile.updated_at = datetime.now(timezone.utc)

        log = LoyaltyPointsLog(
            user_id=user_id,
            transaction_id=transaction_id,
            points_earned=points_earned,
            points_used=0,
            balance_after=profile.loyalty_points,
            reason=f"Purchase reward - {land_id} ({amount} EGP)",
        )
        self.db.add(log)
        await self.db.flush()
        return points_earned

    async def get_loyalty_history(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """Retrieve loyalty points transaction history."""
        from sqlalchemy import select
        q = (
            select(LoyaltyPointsLog)
            .where(LoyaltyPointsLog.user_id == user_id)
            .order_by(LoyaltyPointsLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(q)
        return [
            {
                "log_id": log.log_id,
                "points_earned": log.points_earned,
                "points_used": log.points_used,
                "balance_after": log.balance_after,
                "reason": log.reason,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in result.scalars().all()
        ]