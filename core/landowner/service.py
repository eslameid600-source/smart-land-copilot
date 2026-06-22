"""core.landowner.service — facade re-exporting landowner logic from core.account.investor_service."""

from core.account.investor_service import (  # noqa: F401
    get_or_create_landowner,
    get_owned_lands,
    update_land_status,
    update_commission_settings,
    get_sales_report,
)

__all__ = [
    "get_or_create_landowner",
    "get_owned_lands",
    "update_land_status",
    "update_commission_settings",
    "get_sales_report",
]
