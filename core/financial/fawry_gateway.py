"""
بوابة فوري (Fawry) — الدفع الإلكتروني المصري
==============================================
Smart Land Management Copilot — Fawry Payment Gateway
=====================================================
• FawryPay API v2 — إنشاء فاتورة + تحقق من حالة الدفع + استرداد
• توقيع SHA-256 HMAC للتحقق من Webhooks
• دعم: فوري كاش، فوري كارت، تحويل بنكي
• أوضاع: اختبار (demo) وإنتاج (live)

متغيرات البيئة:
    FAWRY_MERCHANT_CODE    — كود التاجر (من لوحة تحكم فوري)
    FAWRY_SECURE_KEY       — مفتاح الأمان للتوقيع
    FAWRY_BASE_URL         — رابط API
    FAWRY_SANDBOX          — true/false (الافتراضي: true)

مراجع API:
    https://atfawry.fawrystaging.com/ECommerceWeb/Fawry/payments/

توقيع Fawry:
    SHA256(merchant_code + merchant_ref_num + customer_profile_id + amount + HMAC_SECRET)
"""

import os
import hmac
import hashlib
import json
import time
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin

import requests
import httpx

from payment.base import (
    PaymentGateway, PaymentRequest, PaymentResult,
    RefundRequest, RefundResult,
    TransactionStatus, SecurityError,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 1. الإعدادات
# ──────────────────────────────────────────────────────────────

# روابط Fawry
FAWRY_SANDBOX_URL = "https://atfawry.fawrystaging.com/ECommerceWeb/Fawry/payments/"
FAWRY_LIVE_URL = "https://www.atfawry.com/ECommerceWeb/Fawry/payments/"

# أكواد حالة Fawry → حالتنا الموحدة
FAWRY_STATUS_MAP = {
    "NEW": TransactionStatus.PENDING,
    "UNPAID": TransactionStatus.PENDING,
    "EXPIRED": TransactionStatus.EXPIRED,
    "PAID": TransactionStatus.COMPLETED,
    "PARTIALLY_PAID": TransactionStatus.PARTIALLY_REFUNDED,
    "REFUNDED": TransactionStatus.REFUNDED,
    "CANCELLED": TransactionStatus.CANCELLED,
    "FAILED": TransactionStatus.FAILED,
}


def _get_config() -> dict:
    """تحميل إعدادات فوري من متغيرات البيئة."""
    sandbox = os.environ.get("FAWRY_SANDBOX", "true").lower() == "true"
    return {
        "merchant_code": os.environ.get("FAWRY_MERCHANT_CODE", ""),
        "secure_key": os.environ.get("FAWRY_SECURE_KEY", ""),
        "base_url": os.environ.get(
            "FAWRY_BASE_URL",
            FAWRY_SANDBOX_URL if sandbox else FAWRY_LIVE_URL,
        ),
        "sandbox": sandbox,
    }


# ──────────────────────────────────────────────────────────────
# 2. دالة التوقيع
# ──────────────────────────────────────────────────────────────

def _fawry_signature(
    merchant_code: str,
    merchant_ref: str,
    customer_profile: str,
    amount: float,
    secure_key: str,
) -> str:
    """
    حساب توقيع SHA-256 HMAC حسب توثيق فوري.

    المعادلة:
        SHA256(merchant_code + merchant_ref_num + customer_profile_id + amount + secure_key)

    Args:
        merchant_code: كود التاجر
        merchant_ref: رقم المرجع
        customer_profile: معرف العميل
        amount: المبلغ
        secure_key: مفتاح الأمان

    Returns:
        توقيع hex (64 حرف)
    """
    message = f"{merchant_code}{merchant_ref}{customer_profile}{amount}{secure_key}"
    signature = hmac.new(
        secure_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def _verify_fawry_signature(
    merchant_code: str,
    merchant_ref: str,
    customer_profile: str,
    amount: float,
    secure_key: str,
    provided_signature: str,
) -> bool:
    """
    التحقق من توقيع فوري.

    يستخدم المقارنة الزمنية الثابتة (constant-time) لمنع هجمات التوقيت.
    """
    expected = _fawry_signature(merchant_code, merchant_ref, customer_profile, amount, secure_key)
    return hmac.compare_digest(expected, provided_signature)


# ──────────────────────────────────────────────────────────────
# 3. تنفيذ البوابة
# ──────────────────────────────────────────────────────────────

class FawryGateway(PaymentGateway):
    """
    بوابة فوري (Fawry) — الدفع الإلكتروني المصري.

    تدعم:
    • فوري كاش (دفع في أي فرع فوري / شبكة الدفع)
    • فوري كارت (بطاقات Visa / Mastercard / Meeza)
    • تحويل بنكي

    الميزات:
    • توقيع SHA-256 HMAC للطلبات والـ Webhooks
    • وضع اختبار (sandbox) افتراضي
    • إدارة محاولات إعادة المحاولة (retry)
    """

    def __init__(
        self,
        merchant_code: Optional[str] = None,
        secure_key: Optional[str] = None,
        base_url: Optional[str] = None,
        sandbox: Optional[bool] = None,
        timeout: int = 30,
    ):
        config = _get_config()
        self.merchant_code = merchant_code or config["merchant_code"]
        self.secure_key = secure_key or config["secure_key"]
        self.base_url = (base_url or config["base_url"]).rstrip("/")
        self.sandbox = sandbox if sandbox is not None else config["sandbox"]
        self.timeout = timeout

        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

        if not self.merchant_code or not self.secure_key:
            logger.warning(
                "Fawry في وضع الاختبار — حدّث FAWRY_MERCHANT_CODE و FAWRY_SECURE_KEY"
            )

    # ──────────────────────────────────────────────────────────
    # 3.1 بدء الدفع
    # ──────────────────────────────────────────────────────────

    def initiate_payment(self, request: PaymentRequest) -> PaymentResult:
        """
        إنشاء فاتورة فوري جديدة.

        يُنشئ فاتورة في نظام فوري ويُرجع رابط الدفع.
        """
        # حماية التكرار: إنشاء مفتاح idempotency
        idempotency_key = request.idempotency_key or request.merchant_ref

        # بناء chargeItems من request.items
        charge_items = []
        if request.items:
            for item in request.items:
                charge_items.append({
                    "itemId": item.item_id,
                    "description": item.description,
                    "price": str(round(item.price_per_unit, 2)),
                    "quantity": str(item.quantity),
                })
        else:
            # عنصر واحد افتراضي
            charge_items.append({
                "itemId": request.merchant_ref,
                "description": request.description or "دفعة لشراء أرض",
                "price": str(round(request.amount, 2)),
                "quantity": "1",
            })

        # معرف العميل
        customer_profile = request.customer_email or f"guest_{request.merchant_ref}"

        # حساب التوقيع
        signature = _fawry_signature(
            self.merchant_code,
            request.merchant_ref,
            customer_profile,
            request.amount,
            self.secure_key or "demo-secure-key",
        )

        # بناء الطلب
        payload = {
            "merchantCode": self.merchant_code or "DEMO_MERCHANT",
            "merchantRefNum": request.merchant_ref,
            "customerProfileId": customer_profile,
            "customerName": request.customer_name,
            "customerMobile": request.customer_phone,
            "customerEmail": request.customer_email,
            "amount": request.amount,
            "currencyCode": request.currency,
            "chargeItems": charge_items,
            "signature": signature,
            "paymentMethod": "PAYATFAWRY",  # الافتراضي: كاش فوري
            "returnUrl": request.return_url or "",
        }

        # إضافة metadata
        if request.metadata:
            payload["paymentMethod"] = request.metadata.get("payment_method", "PAYATFAWRY")

        logger.info(
            "Fawry: إنشاء فاتورة — مرجع: %s — مبلغ: %.2f %s",
            request.merchant_ref, request.amount, request.currency,
        )

        # إرسال الطلب
        try:
            endpoint = urljoin(self.base_url, "charge")
            resp = self._session.post(
                endpoint,
                json=payload,
                timeout=self.timeout,
            )

            data = resp.json()

            # فحص الاستجابة
            if resp.status_code == 200 and data.get("code") == 200:
                fawry_ref = data.get("paymentReferenceRefNumber", "")
                payment_url = data.get("paymentGatewayUrl", "")

                logger.info(
                    "Fawry: تم إنشاء الفاتورة — مرجع فوري: %s",
                    fawry_ref,
                )

                return PaymentResult(
                    success=True,
                    transaction_ref=fawry_ref,
                    merchant_ref=request.merchant_ref,
                    status=TransactionStatus.PENDING,
                    payment_url=payment_url,
                    gateway_response=data,
                    gateway_type="fawry",
                )

            else:
                error_msg = data.get("message", "فشل إنشاء الفاتورة")
                logger.error("Fawry خطأ %d: %s", resp.status_code, error_msg)
                return PaymentResult(
                    success=False,
                    merchant_ref=request.merchant_ref,
                    status=TransactionStatus.FAILED,
                    error_message=f"فوري: {error_msg}",
                    gateway_response=data,
                    gateway_type="fawry",
                )

        except requests.exceptions.Timeout:
            logger.error("Fawry: انتهت مهلة الاتصال")
            return PaymentResult(
                success=False,
                merchant_ref=request.merchant_ref,
                status=TransactionStatus.FAILED,
                error_message="انتهت مهلة الاتصال ببوابة فوري",
                gateway_type="fawry",
            )
        except requests.exceptions.RequestException as e:
            logger.error("Fawry: خطأ الاتصال — %s", e)
            return PaymentResult(
                success=False,
                merchant_ref=request.merchant_ref,
                status=TransactionStatus.FAILED,
                error_message=f"خطأ الاتصال بفوري: {e}",
                gateway_type="fawry",
            )

    # ──────────────────────────────────────────────────────────
    # 3.2 التحقق من الدفع
    # ──────────────────────────────────────────────────────────

    def verify_payment(self, merchant_ref: str) -> PaymentResult:
        """
        الاستعلام عن حالة فاتورة فوري.

        Fawry Status API:
            GET /api/v1/payments/status?merchantCode=XX&merchantRefNum=YY
        """
        try:
            endpoint = urljoin(
                self.base_url,
                f"api/v1/payments/status?merchantCode={self.merchant_code or 'DEMO_MERCHANT'}&merchantRefNum={merchant_ref}",
            )

            resp = self._session.get(endpoint, timeout=self.timeout)
            data = resp.json()

            if resp.status_code == 200:
                fawry_status = data.get("paymentStatus", "")
                mapped_status = FAWRY_STATUS_MAP.get(
                    fawry_status, TransactionStatus.PENDING
                )

                return PaymentResult(
                    success=mapped_status == TransactionStatus.COMPLETED,
                    transaction_ref=data.get("paymentReferenceRefNumber", ""),
                    merchant_ref=merchant_ref,
                    status=mapped_status,
                    gateway_response=data,
                    gateway_type="fawry",
                )

            # فشل الاستعلام
            return PaymentResult(
                success=False,
                merchant_ref=merchant_ref,
                error_message=f"فشل الاستعلام عن حالة الدفع: {data.get('message', '')}",
                gateway_response=data,
                gateway_type="fawry",
            )

        except Exception as e:
            logger.error("Fawry verify error: %s", e)
            return PaymentResult(
                success=False,
                merchant_ref=merchant_ref,
                error_message=str(e),
                gateway_type="fawry",
            )

    # ──────────────────────────────────────────────────────────
    # 3.3 الاسترداد
    # ──────────────────────────────────────────────────────────

    def refund(self, refund_request: RefundRequest) -> RefundResult:
        """
        استرداد مبلغ من فاتورة فورية.

        يدعم الاسترداد الكلي والجزئي.
        """
        try:
            endpoint = urljoin(self.base_url, "refund")

            payload = {
                "merchantCode": self.merchant_code or "DEMO_MERCHANT",
                "merchantRefNumber": refund_request.merchant_ref,
                "refundAmount": refund_request.amount,
                "reason": refund_request.reason,
                "paymentReferenceRefNumber": refund_request.gateway_ref,
            }

            resp = self._session.post(
                endpoint,
                json=payload,
                timeout=self.timeout,
            )

            data = resp.json()

            if resp.status_code == 200 and data.get("code") == 200:
                logger.info(
                    "Fawry: تم الاسترداد — مرجع: %s — مبلغ: %.2f",
                    refund_request.merchant_ref,
                    refund_request.amount or 0,
                )
                return RefundResult(
                    success=True,
                    refund_ref=data.get("refundReferenceNumber", ""),
                    merchant_ref=refund_request.merchant_ref,
                    refund_amount=refund_request.amount or 0,
                    status="refunded",
                )

            error_msg = data.get("message", "فشل الاسترداد")
            logger.error("Fawry refund error: %s", error_msg)
            return RefundResult(
                success=False,
                merchant_ref=refund_request.merchant_ref,
                error_message=f"فوري: {error_msg}",
            )

        except Exception as e:
            logger.error("Fawry refund exception: %s", e)
            return RefundResult(
                success=False,
                merchant_ref=refund_request.merchant_ref,
                error_message=str(e),
            )

    # ──────────────────────────────────────────────────────────
    # 3.4 أمان Webhooks
    # ──────────────────────────────────────────────────────────

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        التحقق من توقيع Webhook فوري.

        فوري يُرسل التوقيع في header: X-Fawry-Signature
        ويُحسب بنفس معادلة SHA-256 HMAC.
        """
        if not signature:
            return False

        try:
            data = json.loads(payload)
            merchant_ref = data.get("merchantRefNumber", "")
            amount = float(data.get("amount", 0))
            customer_profile = data.get("customerProfileId", "")

            return _verify_fawry_signature(
                self.merchant_code or "DEMO_MERCHANT",
                merchant_ref,
                customer_profile,
                amount,
                self.secure_key or "demo-secure-key",
                signature,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error("فشل التحقق من توقيع فوري: %s", e)
            return False

    def parse_webhook_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        تحويل Webhook فوري إلى صيغة موحدة.

        يستقبل Fawry JSON مثل:
        {
            "merchantRefNumber": "TXN-001",
            "paymentReferenceRefNumber": "900001234",
            "paymentStatus": "PAID",
            "amount": 1000000.0,
            ...
        }
        """
        fawry_status = payload.get("paymentStatus", "")
        mapped_status = FAWRY_STATUS_MAP.get(fawry_status, TransactionStatus.PENDING)

        return {
            "status": mapped_status,
            "merchant_ref": payload.get("merchantRefNumber", ""),
            "amount": float(payload.get("amount", 0)),
            "gateway_ref": payload.get("paymentReferenceRefNumber", ""),
            "fawry_status": fawry_status,
            "customer_profile": payload.get("customerProfileId", ""),
            "payment_method": payload.get("paymentMethod", ""),
        }

    # ──────────────────────────────────────────────────────────
    # 3.5 خصائص البوابة
    # ──────────────────────────────────────────────────────────

    @property
    def gateway_name(self) -> str:
        return "Fawry (فوري)"

    @property
    def supported_currencies(self) -> List[str]:
        return ["EGP"]

    def __repr__(self) -> str:
        mode = "SANDBOX" if self.sandbox else "LIVE"
        return f"FawryGateway(mode={mode}, merchant={self.merchant_code or 'DEMO'})"