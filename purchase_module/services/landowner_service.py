"""purchase_module.services.landowner_service — facade re-exporting landowner logic.

Provides:
    - Module-level functions (re-exported from core.account.investor_service)
    - LandownerService class for OOP-style callers
"""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from core.account.investor_service import (  # noqa: F401
    get_or_create_landowner,
    get_owned_lands,
    update_land_status,
    update_commission_settings,
    get_sales_report,
)


class LandownerService:
    """OOP wrapper around the landowner module-level functions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, user_id: str):
        return await get_or_create_landowner(self.session, user_id)

    async def get_dashboard(self, owner_id: str) -> Dict[str, Any]:
        return await get_owned_lands(self.session, owner_id)

    async def get_owned_lands(self, owner_id: str) -> Dict[str, Any]:
        return await get_owned_lands(self.session, owner_id)

    async def update_land_status(self, owner_id: str, land_id: str, new_status: str) -> Dict[str, Any]:
        return await update_land_status(self.session, owner_id, land_id, new_status)

    async def update_commission_settings(
        self, owner_id: str, land_id: str, broker_pct: float, platform_pct: float
    ) -> Dict[str, Any]:
        return await update_commission_settings(
            self.session, owner_id, land_id, broker_pct, platform_pct
        )

    async def get_sales_report(self, owner_id: str) -> Dict[str, Any]:
        return await get_sales_report(self.session, owner_id)

    async def withdraw(self, owner_id: str, amount_egp: float, method: str = "bank_transfer") -> Dict[str, Any]:
        """Stub withdrawal method."""
        return {
            "user_id": owner_id,
            "withdrawal_id": f"wd-{owner_id}-{int(amount_egp)}",
            "amount_egp": amount_egp,
            "method": method,
            "status": "pending",
        }


__all__ = [
    "get_or_create_landowner",
    "get_owned_lands",
    "update_land_status",
    "update_commission_settings",
    "get_sales_report",
    "LandownerService",
]
