"""
Fawry Pay integration — Egyptian local payment gateway.
Supports: FawryPay (card / wallet / cash collection).

Docs: https://atfawry.fawrystaging.com/ECommerce/api-docs
"""

import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import Optional

import httpx

from purchase_module.gateway.base import PaymentGateway, PaymentResult, GatewayError

logger = logging.getLogger(__name__)

# Default sandbox URL (override via env in production)
FAWRY_BASE_URL = "https://atfawry.fawrystaging.com"
FAWRY_API_KEY = ""
FAWRY_MERCHANT_CODE = ""
FAWRY_HMAC_SECRET = ""
FAWRY_TIMEOUT = 30  # seconds


class FawryGateway(PaymentGateway):
    """Concrete gateway for Fawry Pay (Egypt)."""

    def __init__(
        self,
        base_url: str = FAWRY_BASE_URL,
        api_key: str = FAWRY_API_KEY,
        merchant_code: str = FAWRY_MERCHANT_CODE,
        hmac_secret: str = FAWRY_HMAC_SECRET,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.merchant_code = merchant_code
        self.hmac_secret = hmac_secret

    # ── HMAC signing ──

    def _sign(self, payload: dict) -> str:
        """Generate Fawry HMAC-SHA256 signature."""
        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        digest = hmac.new(
            self.hmac_secret.encode("utf-8"),
            serialized.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return digest.hex()

    # ── Public interface ──

    async def initiate(
        self,
        amount: Decimal,
        merchant_ref: str,
        description: str,
        customer_id: str,
        return_url: Optional[str] = None,
    ) -> PaymentResult:
        payload = {
            "merchantCode": self.merchant_code,
            "merchantRefNum": merchant_ref,
            "customerProfileId": customer_id,
            "amount": str(amount),
            "currencyCode": "EGP",
            "description": description,
            "paymentMethod": "PAYATFAWRY",
            "language": "ar-EG",
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=FAWRY_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/ECommerce/api/v2/paymentRequest",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            logger.error("Fawry initiate failed %s: %s", exc.response.status_code, body)
            raise GatewayError("fawry", body, exc.response.status_code) from exc
        except httpx.RequestError as exc:
            logger.error("Fawry connection error: %s", exc)
            raise GatewayError("fawry", str(exc)) from exc

        if data.get("statusCode") not in (200, 201, "200"):
            msg = data.get("statusDescription", "Unknown Fawry error")
            raise GatewayError("fawry", msg)

        return PaymentResult(
            success=True,
            payment_url=data.get("paymentUrl", ""),
            gateway_ref=data.get("referenceNumber", ""),
            message="Payment initiated via Fawry",
        )

    async def verify(self, gateway_ref: str) -> PaymentResult:
        params = {
            "merchantCode": self.merchant_code,
            "merchantRefNum": gateway_ref,
        }
        headers = {"Authorization": self.api_key}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}/ECommerce/api/v2/paymentStatus",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise GatewayError("fawry", str(exc)) from exc

        payment_status = data.get("paymentStatus", "")
        is_paid = payment_status == "PAID"

        return PaymentResult(
            success=is_paid,
            gateway_ref=gateway_ref,
            message=f"Fawry status: {payment_status}",
        )

    async def refund(
        self, gateway_ref: str, amount: Decimal, reason: str = ""
    ) -> PaymentResult:
        payload = {
            "merchantCode": self.merchant_code,
            "merchantRefNum": gateway_ref,
            "refundAmount": str(amount),
            "currencyCode": "EGP",
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=FAWRY_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/ECommerce/api/v2/refund",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise GatewayError("fawry", str(exc)) from exc

        return PaymentResult(
            success=data.get("statusCode") == 200,
            gateway_ref=gateway_ref,
            message=data.get("statusDescription", ""),
        )