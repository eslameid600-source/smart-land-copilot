"""core.incentive.service — facade re-exporting incentive logic from core.account.investor_service."""

from core.account.investor_service import (  # noqa: F401
    REPEAT_BUYER_THRESHOLD,
    REPEAT_BUYER_DISCOUNT,
    POINTS_PER_10K_EGP,
    POINTS_REDEMPTION_RATE,
    MAX_TOTAL_DISCOUNT_PCT,
    calculate_incentive,
    redeem_loyalty_points,
)

__all__ = [
    "REPEAT_BUYER_THRESHOLD",
    "REPEAT_BUYER_DISCOUNT",
    "POINTS_PER_10K_EGP",
    "POINTS_REDEMPTION_RATE",
    "MAX_TOTAL_DISCOUNT_PCT",
    "calculate_incentive",
    "redeem_loyalty_points",
]
