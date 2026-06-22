"""
Stripe integration — for international card payments.
Uses Stripe Checkout Sessions (hosted payment page).

Docs: https://docs.stripe.com/api/checkout/sessions
"""

import logging
from decimal import Decimal
from typing import Optional

from purchase_module.gateway.base import GatewayError, PaymentGateway, PaymentResult

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = ""
STRIPE_WEBHOOK_SECRET = ""


class StripeGateway(PaymentGateway):
    """Concrete gateway for Stripe (international cards)."""

    def __init__(self, secret_key: str = STRIPE_SECRET_KEY):
        self.secret_key = secret_key
        self._stripe = None

    def _get_stripe(self):
        """Lazy-load stripe module (not everyone needs it)."""
        if self._stripe is None:
            import stripe
            stripe.api_key = self.secret_key
            self._stripe = stripe
        return self._stripe

    async def initiate(
        self,
        amount: Decimal,
        merchant_ref: str,
        description: str,
        customer_id: str,
        return_url: Optional[str] = None,
    ) -> PaymentResult:
        stripe = self._get_stripe()
        amount_cents = int(amount * 100)

        success_url = return_url or "https://smartland.eg/payment/success"
        cancel_url = return_url or "https://smartland.eg/payment/cancel"

        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "egp",
                        "product_data": {"name": description},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }],
                mode="payment",
                metadata={"merchant_ref": merchant_ref, "customer_id": customer_id},
                success_url=f"{success_url}?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=cancel_url,
            )
        except Exception as exc:
            logger.error("Stripe session creation failed: %s", exc)
            raise GatewayError("stripe", str(exc)) from exc

        return PaymentResult(
            success=True,
            payment_url=session.url,
            gateway_ref=session.id,
            message="Checkout session created",
        )

    async def verify(self, gateway_ref: str) -> PaymentResult:
        stripe = self._get_stripe()
        try:
            session = stripe.checkout.Session.retrieve(gateway_ref)
        except Exception as exc:
            raise GatewayError("stripe", str(exc)) from exc

        return PaymentResult(
            success=session.payment_status == "paid",
            gateway_ref=gateway_ref,
            message=f"Stripe payment_status: {session.payment_status}",
        )

    async def refund(
        self, gateway_ref: str, amount: Decimal, reason: str = ""
    ) -> PaymentResult:
        stripe = self._get_stripe()
        amount_cents = int(amount * 100)
        try:
            refund = stripe.refund.create(
                payment_intent=gateway_ref,
                amount=amount_cents,
                reason="requested_by_customer" if reason else None,
            )
        except Exception as exc:
            raise GatewayError("stripe", str(exc)) from exc

        return PaymentResult(
            success=refund.status in ("succeeded", "pending"),
            gateway_ref=gateway_ref,
            message=f"Refund {refund.id}: {refund.status}",
        )