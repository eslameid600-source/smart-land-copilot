"""
Smart Land Management Copilot V4.0
نظام الدفع والمعاملات المالية — كود Python (FastAPI) كامل
"""

# ============================================================
# config/payment.py — إعدادات بوابة الدفع
# ============================================================

from pydantic_settings import BaseSettings


class PaymentSettings(BaseSettings):
    """إعدادات بوابات الدفع"""

    # فوري المصري
    FAWRY_API_KEY: str = ""
    FAWRY_MERCHANT_CODE: str = ""
    FAWRY_BASE_URL: str = "https://atfawry.fawrystaging.com"
    FAWRY_HMAC_SECRET: str = ""

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLIC_KEY: str = ""

    # PayPal
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_BASE_URL: str = "https://api-m.sandbox.paypal.com"

    # عمولة المنصة وضريبة التصرفات العقارية
    PLATFORM_COMMISSION_RATE: float = 0.015   # 1.5%
    REAL_ESTATE_TAX_RATE: float = 0.025       # 2.5%

    # مهلة انتهاء صلاحية المعاملة (بالدقائق)
    TRANSACTION_TIMEOUT_MINUTES: int = 30

    model_config = {"env_prefix": "PAYMENT_"}


payment_settings = PaymentSettings()


# ============================================================
# core/payment/models.py — نماذج البيانات
# ============================================================

from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
from enum import Enum


class TransactionStatus(str, Enum):
    PENDING = "Pending"
    COMPLETED = "Completed"
    FAILED = "Failed"
    REFUNDED = "Refunded"


class PaymentMethod(str, Enum):
    FAWRY = "fawry"
    STRIPE = "stripe"
    PAYPAL = "paypal"


class PaymentInitRequest(BaseModel):
    land_id: str = Field(..., min_length=1, description="معرف الأرض")
    payment_method: PaymentMethod = Field(
        default=PaymentMethod.FAWRY,
        description="بوابة الدفع",
    )


class TransactionResponse(BaseModel):
    transaction_id: str
    land_id: str
    buyer_id: str
    seller_id: str
    amount_egp: float
    platform_fee_egp: float
    tax_amount_egp: float
    status: TransactionStatus
    payment_method: PaymentMethod
    gateway_ref: Optional[str] = None
    payment_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookCallback(BaseModel):
    transaction_id: str
    status: TransactionStatus
    gateway_ref: Optional[str] = None
    gateway_message: Optional[str] = None


# ============================================================
# core/payment/gateway.py — واجهة بوابات الدفع (Strategy Pattern)
# ============================================================

from abc import ABC, abstractmethod
import httpx
import hmac
import hashlib
import base64
import json
import logging

logger = logging.getLogger(__name__)


class PaymentGateway(ABC):
    """واجهة مجردة لبوابات الدفع - Strategy Pattern"""

    @abstractmethod
    async def initiate_payment(
        self, amount: float, ref: str, description: str
    ) -> dict:
        """بدء عملية الدفع وإرجاع رابط الدفع"""
        ...

    @abstractmethod
    async def verify_payment(self, ref: str) -> dict:
        """التحقق من حالة المعاملة لدى البوابة"""
        ...

    @abstractmethod
    async def refund(self, ref: str, amount: float) -> dict:
        """استرداد المبلغ"""
        ...


class FawryGateway(PaymentGateway):
    """تكامل مع فوري المصري (Fawry Pay)"""

    def __init__(self):
        self.base_url = payment_settings.FAWRY_BASE_URL
        self.api_key = payment_settings.FAWRY_API_KEY
        self.merchant_code = payment_settings.FAWRY_MERCHANT_CODE
        self.hmac_secret = payment_settings.FAWRY_HMAC_SECRET

    def _sign(self, payload: dict) -> str:
        """توقيع الطلب HMAC-SHA256"""
        message = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        signature = hmac.new(
            self.hmac_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(signature).decode()

    async def initiate_payment(
        self, amount: float, ref: str, description: str
    ) -> dict:
        payload = {
            "merchantCode": self.merchant_code,
            "merchantRefNum": ref,
            "customerProfileId": ref.split("_")[0],
            "amount": str(amount),
            "currencyCode": "EGP",
            "description": description,
            "paymentMethod": "PAYATFAWRY",
            "language": "ar-EG",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/ECommerce/api/v2/paymentRequest",
                json=payload,
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        resp.raise_for_status()
        data = resp.json()
        return {
            "payment_url": data.get("paymentUrl", ""),
            "gateway_ref": data.get("referenceNumber", ""),
        }

    async def verify_payment(self, ref: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/ECommerce/api/v2/paymentStatus",
                params={"merchantCode": self.merchant_code, "merchantRefNum": ref},
                headers={"Authorization": self.api_key},
                timeout=15.0,
            )
        resp.raise_for_status()
        return resp.json()

    async def refund(self, ref: str, amount: float) -> dict:
        payload = {
            "merchantCode": self.merchant_code,
            "merchantRefNum": ref,
            "refundAmount": str(amount),
            "currencyCode": "EGP",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/ECommerce/api/v2/refund",
                json=payload,
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        resp.raise_for_status()
        return resp.json()


class StripeGateway(PaymentGateway):
    """تكامل مع Stripe للبطاقات الدولية"""

    def __init__(self):
        import stripe
        stripe.api_key = payment_settings.STRIPE_SECRET_KEY
        self.stripe = stripe

    async def initiate_payment(
        self, amount: float, ref: str, description: str
    ) -> dict:
        amount_cents = int(amount * 100)
        session = self.stripe.checkout.Session.create(
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
            metadata={"merchant_ref": ref},
            success_url="https://smartland.eg/success?ref={CHECKOUT_SESSION_ID}",
            cancel_url="https://smartland.eg/cancel?ref={CHECKOUT_SESSION_ID}",
        )
        return {
            "payment_url": session.url,
            "gateway_ref": session.id,
        }

    async def verify_payment(self, ref: str) -> dict:
        session = self.stripe.checkout.Session.retrieve(ref)
        return {"status": "COMPLETED" if session.payment_status == "paid" else "PENDING"}

    async def refund(self, ref: str, amount: float) -> dict:
        refund = self.stripe.refund.create(
            payment_intent=ref,
            amount=int(amount * 100),
        )
        return {"status": refund.status, "refund_id": refund.id}


class PayPalGateway(PaymentGateway):
    """تكامل مع PayPal"""

    def __init__(self):
        self.base_url = payment_settings.PAYPAL_BASE_URL
        self.client_id = payment_settings.PAYPAL_CLIENT_ID
        self.client_secret = payment_settings.PAYPAL_CLIENT_SECRET

    async def _get_access_token(self) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                timeout=15.0,
            )
        resp.raise_for_status()
        return resp.json()["access_token"]

    async def initiate_payment(
        self, amount: float, ref: str, description: str
    ) -> dict:
        token = await self._get_access_token()
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": ref,
                "description": description,
                "amount": {
                    "currency_code": "EGP",
                    "value": str(amount),
                },
            }],
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v2/checkout/orders",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        resp.raise_for_status()
        data = resp.json()
        links = {l["rel"]: l["href"] for l in data.get("links", [])}
        return {
            "payment_url": links.get("approve", ""),
            "gateway_ref": data["id"],
        }

    async def verify_payment(self, ref: str) -> dict:
        token = await self._get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v2/checkout/orders/{ref}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
        resp.raise_for_status()
        data = resp.json()
        return {"status": data.get("status", "UNKNOWN")}

    async def refund(self, ref: str, amount: float) -> dict:
        token = await self._get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v2/payments/captures/{ref}/refund",
                json={"amount": {"currency_code": "EGP", "value": str(amount)}},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        resp.raise_for_status()
        return resp.json()


# ============================================================
# core/payment/service.py — منطق المعاملات
# ============================================================

import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from infrastructure.database.models import Land, Transaction, Investor, Landowner
from core.payment.gateway import FawryGateway, StripeGateway, PayPalGateway
from core.payment.models import (
    TransactionStatus,
    PaymentMethod,
    PaymentInitRequest,
    TransactionResponse,
    WebhookCallback,
)

GATEWAYS = {
    "fawry": FawryGateway,
    "stripe": StripeGateway,
    "paypal": PayPalGateway,
}


async def initiate_payment(
    db: AsyncSession,
    buyer_id: str,
    body: PaymentInitRequest,
) -> TransactionResponse:
    """بدء عملية دفع جديدة"""
    # 1. التحقق من الأرض وحالتها
    land = await db.get(Land, body.land_id)
    if not land or land.status != "Available":
        raise ValueError("الأرض غير متاحة للبيع")

    # 2. حساب الرسوم والضرائب
    tax = round(land.price_egp * payment_settings.REAL_ESTATE_TAX_RATE, 2)
    fee = round(land.price_egp * payment_settings.PLATFORM_COMMISSION_RATE, 2)

    # 3. إنشاء المعاملة
    tx_id = str(uuid.uuid4())
    gateway = GATEWAYS[body.payment_method.value]()
    ref = f"{buyer_id}_{body.land_id}_{tx_id[:8]}"

    transaction = Transaction(
        transaction_id=tx_id,
        land_id=body.land_id,
        buyer_id=buyer_id,
        seller_id=land.owner_id,
        amount_egp=land.price_egp,
        platform_fee_egp=fee,
        tax_amount_egp=tax,
        status=TransactionStatus.PENDING,
        payment_method=body.payment_method,
    )
    db.add(transaction)
    await db.commit()

    # 4. استدعاء بوابة الدفع
    try:
        result = await gateway.initiate_payment(
            amount=land.price_egp,
            ref=ref,
            description=f"شراء أرض - {body.land_id}",
        )
        transaction.gateway_ref = result.get("gateway_ref")
        await db.commit()
    except Exception as e:
        transaction.status = TransactionStatus.FAILED
        await db.commit()
        logger.error(f"Payment initiation failed: {e}")
        raise

    return TransactionResponse(
        transaction_id=tx_id,
        payment_url=result.get("payment_url"),
        land_id=body.land_id,
        buyer_id=buyer_id,
        seller_id=land.owner_id,
        amount_egp=land.price_egp,
        platform_fee_egp=fee,
        tax_amount_egp=tax,
        status=TransactionStatus.PENDING,
        payment_method=body.payment_method,
        gateway_ref=result.get("gateway_ref"),
        created_at=transaction.created_at,
    )


async def handle_webhook(
    db: AsyncSession,
    gateway_name: str,
    callback: WebhookCallback,
) -> None:
    """معالجة إشعار من بوابة الدفع"""
    transaction = await db.get(Transaction, callback.transaction_id)
    if not transaction:
        raise ValueError("المعاملة غير موجودة")

    transaction.status = callback.status
    transaction.updated_at = datetime.now(timezone.utc)

    if callback.status == TransactionStatus.COMPLETED:
        transaction.completed_at = datetime.now(timezone.utc)
        # تحديث حالة الأرض
        land = await db.get(Land, transaction.land_id)
        if land:
            land.status = "Sold"
            land.current_owner_id = transaction.buyer_id

        # تحديث حساب البائع
        owner = await db.get(Landowner, transaction.seller_id)
        if owner:
            net = transaction.amount_egp - transaction.platform_fee_egp
            owner.total_sales_egp += net
            owner.total_lands_sold += 1

        # تحديث حساب المستثمر (المشتري)
        investor = await db.get(Investor, transaction.buyer_id)
        if investor:
            investor.total_lands_purchased += 1
            investor.total_invested_egp += transaction.amount_egp

    await db.commit()


async def get_transaction_history(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    per_page: int = 20,
) -> list[Transaction]:
    """سجل المعاملات المالية للمستخدم"""
    offset = (page - 1) * per_page
    result = await db.execute(
        select(Transaction)
        .where(
            (Transaction.buyer_id == user_id)
            | (Transaction.seller_id == user_id)
        )
        .order_by(Transaction.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    return list(result.scalars().all())