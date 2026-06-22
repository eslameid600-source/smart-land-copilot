"""core.investor.service — facade re-exporting investor logic from core.account.investor_service."""

from core.account.investor_service import (  # noqa: F401
    get_or_create_investor,
    get_wallet,
    get_investment_history,
    record_purchase,
)

__all__ = [
    "get_or_create_investor",
    "get_wallet",
    "get_investment_history",
    "record_purchase",
]
