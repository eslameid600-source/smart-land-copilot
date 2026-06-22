"""purchase_module.services.incentive_service — facade re-exporting incentive logic.

Imports from core.account.investor_service (where calculate_incentive and
REPEAT_BUYER_THRESHOLD are actually defined) — NOT from core.account.incentive_service
(which only exports IncentiveService class).
"""


from core.account.investor_service import (  # noqa: F401
    REPEAT_BUYER_THRESHOLD,
    REPEAT_BUYER_DISCOUNT,
    POINTS_PER_10K_EGP,
    POINTS_REDEMPTION_RATE,
    MAX_TOTAL_DISCOUNT_PCT,
    calculate_incentive,
    redeem_loyalty_points,
)
from core.account.incentive_service import IncentiveService  # noqa: F401

# Re-export the registration discount constant from the sibling investor_service module
from purchase_module.services.investor_service import REGISTRATION_DISCOUNT_PCT  # noqa: F401

__all__ = [
    "REPEAT_BUYER_THRESHOLD",
    "REPEAT_BUYER_DISCOUNT",
    "POINTS_PER_10K_EGP",
    "POINTS_REDEMPTION_RATE",
    "MAX_TOTAL_DISCOUNT_PCT",
    "calculate_incentive",
    "redeem_loyalty_points",
    "IncentiveService",
    "REGISTRATION_DISCOUNT_PCT",
]
