"""
Abstract payment gateway interface (Strategy Pattern).
All concrete gateways must implement these three methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from decimal import Decimal


@dataclass(frozen=True)
class PaymentResult:
    """Immutable result returned by a gateway after initiating payment."""
    success: bool
    payment_url: str = ""
    gateway_ref: str = ""
    message: str = ""


class PaymentGateway(ABC):
    """
    Abstract base for payment gateways.
    Each gateway (Fawry, Stripe, Meeza, etc.) implements these methods.
    """

    @abstractmethod
    async def initiate(
        self,
        amount: Decimal,
        merchant_ref: str,
        description: str,
        customer_id: str,
        return_url: Optional[str] = None,
    ) -> PaymentResult:
        """
        Start a payment and return a URL the user can redirect to.
        Raises GatewayError on connectivity / validation failures.
        """
        ...

    @abstractmethod
    async def verify(self, gateway_ref: str) -> PaymentResult:
        """
        Check the current status of a payment with the gateway.
        Used by webhooks or polling to confirm payment completion.
        """
        ...

    @abstractmethod
    async def refund(
        self, gateway_ref: str, amount: Decimal, reason: str = ""
    ) -> PaymentResult:
        """
        Initiate a refund for a previously completed payment.
        """
        ...


class GatewayError(Exception):
    """Raised when a payment gateway call fails."""
    def __init__(self, gateway: str, message: str, status_code: int = 502):
        self.gateway = gateway
        self.status_code = status_code
        super().__init__(f"[{gateway}] {message}")