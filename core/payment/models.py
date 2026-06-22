"""core.payment.models — facade with payment Pydantic schemas + PaymentTransaction ORM model.

Provides:
    - PaymentTransaction (re-exported from core.account.models)
    - PaymentInitRequest, TransactionResponse, WebhookCallback (Pydantic schemas)
"""

from typing import Optional

from pydantic import BaseModel, Field

from core.account.models import PaymentTransaction  # noqa: F401


# ──────────────────────────────────────────────
# Pydantic request/response schemas
# ──────────────────────────────────────────────

class PaymentInitRequest(BaseModel):
    """Request body for initiating a payment."""

    land_id: str = Field(..., description="معرّف الأرض المراد شراؤها")
    amount_egp: float = Field(..., gt=0, description="المبلغ بالجنيه المصري")
    payment_method: str = Field("wallet", description="wallet / fawry / stripe / paypal")
    currency: str = Field("EGP")
    idempotency_key: Optional[str] = Field(None, description="مفتاح Idempotency لمنع التكرار")
    metadata: Optional[dict] = Field(None, description="بيانات إضافية")


class TransactionResponse(BaseModel):
    """Response body after initiating/processing a payment."""

    payment_id: str
    transaction_id: Optional[str] = None
    status: str = Field(..., description="pending / succeeded / failed / refunded")
    amount_egp: float
    currency: str = "EGP"
    provider: Optional[str] = None
    provider_txn_ref: Optional[str] = None
    created_at: Optional[str] = None
    failure_reason: Optional[str] = None
    redirect_url: Optional[str] = None


class WebhookCallback(BaseModel):
    """Body for incoming webhook from payment gateway."""

    gateway: str = Field(..., description="fawry / stripe / paypal / paymob")
    event_type: str
    payment_id: str
    transaction_id: Optional[str] = None
    amount_egp: Optional[float] = None
    currency: Optional[str] = "EGP"
    status: str
    signature: Optional[str] = None
    raw_payload: Optional[dict] = None
    received_at: Optional[str] = None


__all__ = [
    "PaymentTransaction",
    "PaymentInitRequest",
    "TransactionResponse",
    "WebhookCallback",
]
