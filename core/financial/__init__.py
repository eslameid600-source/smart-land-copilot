"""
Payment Gateway — package init
"""

from purchase_module.gateway.base import PaymentGateway, PaymentResult
from purchase_module.gateway.fawry import FawryGateway
from purchase_module.gateway.stripe_gateway import StripeGateway

__all__ = [
    "PaymentGateway",
    "PaymentResult",
    "FawryGateway",
    "StripeGateway",
]

GATEWAY_REGISTRY: dict[str, type[PaymentGateway]] = {
    "fawry": FawryGateway,
    "stripe": StripeGateway,
}