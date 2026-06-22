"""core.financial.base — facade with abstract financial primitives."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class FinancialServiceBase(ABC):
    """Abstract base for financial operations."""

    @abstractmethod
    async def debit(self, user_id: str, amount: float, reason: str = "") -> Dict[str, Any]:
        ...

    @abstractmethod
    async def credit(self, user_id: str, amount: float, reason: str = "") -> Dict[str, Any]:
        ...

    @abstractmethod
    async def freeze(self, user_id: str, amount: float) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def unfreeze(self, user_id: str, amount: float) -> Dict[str, Any]:
        ...


class StubFinancialService(FinancialServiceBase):
    """In-memory stub for tests/dev — delegates to InvestorStore when possible."""

    async def debit(self, user_id, amount, reason=""):
        return {"user_id": user_id, "amount": -amount, "reason": reason, "status": "ok"}

    async def credit(self, user_id, amount, reason=""):
        return {"user_id": user_id, "amount": amount, "reason": reason, "status": "ok"}

    async def freeze(self, user_id, amount):
        return {"user_id": user_id, "frozen": amount, "status": "ok"}

    async def unfreeze(self, user_id, amount):
        return {"user_id": user_id, "unfrozen": amount, "status": "ok"}


class PaymentRouter:
    """Routes payment requests to the appropriate provider (stub).

    Real implementation should integrate with Fawry / Stripe / Paymob.
    """

    def __init__(self, default_provider: str = "wallet"):
        self.default_provider = default_provider

    async def charge(self, user_id: str, amount: float, provider: str | None = None, **kwargs):
        provider = provider or self.default_provider
        return {
            "user_id": user_id,
            "amount": amount,
            "provider": provider,
            "status": "succeeded",
            "payment_id": f"pay-{user_id}-{int(amount)}",
        }

    async def refund(self, payment_id: str, amount: float | None = None):
        return {"payment_id": payment_id, "status": "refunded", "amount": amount or 0}


__all__ = ["FinancialServiceBase", "StubFinancialService", "PaymentRouter"]
