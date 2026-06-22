"""purchase_module.services.investor_service — facade re-exporting investor logic.

Adds REGISTRATION_DISCOUNT_PCT + InvestorService stub used by core/account tests.
"""

from decimal import Decimal
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from core.account.investor_service import (  # noqa: F401
    get_or_create_investor,
    get_wallet,
    get_investment_history,
    record_purchase,
    REPEAT_BUYER_THRESHOLD,
    calculate_incentive,
)
from core.account.incentive_service import IncentiveService  # noqa: F401

# Discount applied to registration fees for repeat buyers
REGISTRATION_DISCOUNT_PCT = Decimal("2.0")


class InvestorService:
    """Service facade for investor operations.

    Wraps the module-level functions in core.account.investor_service
    so tests can instantiate a single service object.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, user_id: str):
        return await get_or_create_investor(self.session, user_id)

    async def get_wallet(self, user_id: str) -> Dict[str, Any]:
        return await get_wallet(self.session, user_id)

    async def get_investment_history(self, user_id: str, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        return await get_investment_history(self.session, user_id, page=page, per_page=per_page)

    async def record_purchase(
        self,
        user_id: str,
        land_id: str,
        transaction_id: str,
        purchase_price: float,
        discount_applied: float = 0,
    ) -> None:
        return await record_purchase(
            self.session, user_id, land_id, transaction_id, purchase_price, discount_applied
        )


__all__ = [
    "get_or_create_investor",
    "get_wallet",
    "get_investment_history",
    "record_purchase",
    "REPEAT_BUYER_THRESHOLD",
    "calculate_incentive",
    "REGISTRATION_DISCOUNT_PCT",
    "IncentiveService",
    "InvestorService",
]
