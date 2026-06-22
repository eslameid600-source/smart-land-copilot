"""services.financial_service — facade re-exporting from core.financial.base."""

from core.financial.base import (  # noqa: F401
    FinancialServiceBase,
    StubFinancialService,
    PaymentRouter,
)


class FinancialService(StubFinancialService):
    """Concrete financial service used by UI layers.

    Inherits the stub debit/credit/freeze/unfreeze behavior from
    StubFinancialService. Replace with real implementation in production.
    """

    def get_summary(self, user_id: str) -> dict:
        """Return a financial summary for a user (stub)."""
        return {
            "user_id": user_id,
            "wallet_balance_egp": 0.0,
            "frozen_balance_egp": 0.0,
            "total_spent_egp": 0.0,
            "total_sales_egp": 0.0,
        }


__all__ = ["FinancialServiceBase", "StubFinancialService", "PaymentRouter", "FinancialService"]
