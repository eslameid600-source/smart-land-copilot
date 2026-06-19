"""
Smart Land Copilot — ERP Integration Module
=============================================
تكامل مع أنظمة ERP (Odoo, SAP, Microsoft Dynamics, أو أي نظام محاسبة).

الوظائف:
    1. `sync_transaction_to_erp()` — إرسال بيانات المعاملة إلى ERP
    2. `sync_land_to_erp()` — مزامنة الأراضي كمخزون في ERP
    3. `get_erp_inventory_status()` — جلب حالة المخزون من ERP
    4. `sync_broker_commission()` — مزامنة العمولات مع ERP

الإعدادات:
    - ERP_ENABLED: تفعيل/إيقاف التكامل
    - ERP_API_URL: رابط نظام ERP
    - ERP_API_KEY: مفتاح API
    - ERP_SYSTEM: نوع النظام (odoo, sap, dynamics, custom)
"""

import os
import json
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# الإعدادات
# ──────────────────────────────────────────────

ERP_ENABLED = os.getenv("ERP_ENABLED", "false").lower() == "true"
ERP_API_URL = os.getenv("ERP_API_URL", "http://localhost:8069")  # Odoo default
ERP_API_KEY = os.getenv("ERP_API_KEY", "")
ERP_SYSTEM = os.getenv("ERP_SYSTEM", "odoo")  # odoo, sap, dynamics, custom
ERP_TIMEOUT_SEC = int(os.getenv("ERP_TIMEOUT_SEC", "10"))


# ──────────────────────────────────────────────
# نماذج البيانات
# ──────────────────────────────────────────────

@dataclass
class ERPSyncResult:
    """نتيجة مزامنة مع ERP."""
    success: bool
    erp_reference: str = ""
    message: str = ""
    error: Optional[str] = None
    synced_at: str = ""


@dataclass
class ERPTransactionPayload:
    """بيانات المعاملة المرسلة إلى ERP."""
    transaction_id: str
    land_id: str
    buyer_id: str
    buyer_name: str = ""
    seller_id: str
    seller_name: str = ""
    broker_id: Optional[str] = None
    broker_name: str = ""
    sale_price_egp: float
    commission_egp: float = 0.0
    platform_fee_egp: float = 0.0
    net_to_seller_egp: float = 0.0
    tax_amount_egp: float = 0.0
    transaction_date: str = ""
    payment_method: str = "wallet"
    status: str = "Completed"
    notes: str = ""


@dataclass
class ERPLandPayload:
    """بيانات الأرض المرسلة إلى ERP كمخزون."""
    land_id: str
    owner_id: str
    owner_name: str = ""
    governorate: str
    region_city: str = ""
    total_area_sqm: float
    price_per_sqm_egp: float
    total_price_egp: float
    status: str  # Available, Sold, Reserved
    usage_type: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ──────────────────────────────────────────────
# توقيع API (HMAC)
# ──────────────────────────────────────────────

def _sign_payload(payload: dict) -> str:
    """توقيع الحمولة بـ HMAC-SHA256 لمصادقة الطلب."""
    if not ERP_API_KEY:
        return ""
    payload_str = json.dumps(payload, sort_keys=True, default=str)
    return hmac.new(
        ERP_API_KEY.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()


def _build_headers() -> dict:
    """بناء هيدرات الطلب مع التوقيع."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SmartLandCopilot/1.0",
        "X-ERP-System": ERP_SYSTEM,
    }
    if ERP_API_KEY:
        headers["X-API-Key"] = ERP_API_KEY
    return headers


# ──────────────────────────────────────────────
# دالة الاتصال بنظام ERP
# ──────────────────────────────────────────────

async def _call_erp(
    endpoint: str,
    payload: dict,
    method: str = "POST",
) -> dict:
    """
    إرسال طلب إلى نظام ERP.
    تستخدم httpx للاتصال غير المتزامن مع timeout.

    Args:
        endpoint: نقطة النهاية (مثل /api/sale.order)
        payload: الحمولة
        method: طريقة HTTP

    Returns:
        dict مع نتيجة الاتصال
    """
    if not ERP_ENABLED:
        logger.info(f"ERP disabled — skipping {endpoint}")
        return {"success": True, "erp_reference": "skipped-disabled", "message": "ERP integration disabled"}

    if not ERP_API_URL:
        logger.warning("ERP_API_URL not set — cannot sync")
        return {"success": False, "error": "ERP_API_URL not configured"}

    url = f"{ERP_API_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = _build_headers()
    signature = _sign_payload(payload)
    if signature:
        headers["X-Signature"] = signature

    try:
        import httpx
        async with httpx.AsyncClient(timeout=ERP_TIMEOUT_SEC) as client:
            if method.upper() == "POST":
                response = await client.post(url, json=payload, headers=headers)
            elif method.upper() == "PUT":
                response = await client.put(url, json=payload, headers=headers)
            else:
                response = await client.get(url, params=payload, headers=headers)

            if response.status_code in (200, 201):
                data = response.json()
                logger.info(f"ERP sync successful: {endpoint} — ref={data.get('id', 'N/A')}")
                return {
                    "success": True,
                    "erp_reference": str(data.get("id", data.get("reference", ""))),
                    "message": "Synced successfully",
                    "data": data,
                }
            else:
                logger.error(f"ERP sync failed: {endpoint} — status={response.status_code}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text[:200]}",
                }

    except ImportError:
        logger.warning("httpx not installed — using stub ERP mode")
        return _stub_erp_call(endpoint, payload)
    except Exception as e:
        logger.error(f"ERP connection error: {e}")
        return {"success": False, "error": str(e)}


def _stub_erp_call(endpoint: str, payload: dict) -> dict:
    """
    وضع الاختبار — يحاكي استجابة ERP دون اتصال حقيقي.
    يُستخدم عندما لا يكون httpx متاحاً أو عند التطوير.
    """
    logger.info(f"🔄 [ERP Stub] {endpoint} — payload keys={list(payload.keys())}")
    return {
        "success": True,
        "erp_reference": f"STUB-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hashlib.md5(str(payload).encode(), usedforsecurity=False).hexdigest()[:8]}",
        "message": "Stub ERP — no real connection",
        "data": {"id": 0, "state": "draft"},
    }


# ──────────────────────────────────────────────
# 1. مزامنة المعاملة مع ERP
# ──────────────────────────────────────────────

async def sync_transaction_to_erp(
    transaction_id: str,
    land_id: str = "",
    buyer_id: str = "",
    buyer_name: str = "",
    seller_id: str = "",
    seller_name: str = "",
    sale_price_egp: float = 0.0,
    commission_egp: float = 0.0,
    broker_id: Optional[str] = None,
    broker_name: str = "",
    platform_fee_egp: float = 0.0,
    net_to_seller_egp: float = 0.0,
    payment_method: str = "wallet",
    notes: str = "",
) -> ERPSyncResult:
    """
    إرسال بيانات المعاملة المالية إلى نظام ERP.

    في Odoo: ينشئ Sale Order + Invoice
    في SAP: ينشئ Accounting Document
    في أنظمة أخرى: JSON عام

    Args:
        transaction_id: معرف المعاملة في النظام
        land_id: معرف الأرض
        buyer_id: معرف المشتري
        buyer_name: اسم المشتري
        seller_id: معرف البائع
        seller_name: اسم البائع
        sale_price_egp: سعر البيع
        commission_egp: العمولة
        broker_id: معرف الوسيط (اختياري)
        broker_name: اسم الوسيط
        platform_fee_egp: رسوم المنصة
        net_to_seller_egp: صافي البائع
        payment_method: طريقة الدفع
        notes: ملاحظات إضافية

    Returns:
        ERPSyncResult
    """
    payload = ERPTransactionPayload(
        transaction_id=transaction_id,
        land_id=land_id,
        buyer_id=buyer_id,
        buyer_name=buyer_name,
        seller_id=seller_id,
        seller_name=seller_name,
        broker_id=broker_id,
        broker_name=broker_name,
        sale_price_egp=sale_price_egp,
        commission_egp=commission_egp,
        platform_fee_egp=platform_fee_egp,
        net_to_seller_egp=net_to_seller_egp,
        transaction_date=datetime.now(timezone.utc).isoformat(),
        payment_method=payment_method,
        status="Completed",
        notes=notes,
    )

    # اختيار نقطة النهاية حسب نظام ERP
    endpoints = {
        "odoo": "/api/sale.order",
        "sap": "/api/accounting/document",
        "dynamics": "/api/sales/invoice",
        "custom": "/api/transactions",
    }
    endpoint = endpoints.get(ERP_SYSTEM, endpoints["custom"])

    result = await _call_erp(endpoint, asdict(payload))

    return ERPSyncResult(
        success=result.get("success", False),
        erp_reference=result.get("erp_reference", ""),
        message=result.get("message", ""),
        error=result.get("error"),
        synced_at=datetime.now(timezone.utc).isoformat(),
    )


# ──────────────────────────────────────────────
# 2. مزامنة الأرض كمخزون في ERP
# ──────────────────────────────────────────────

async def sync_land_to_erp(
    land_id: str,
    owner_id: str,
    owner_name: str = "",
    governorate: str = "",
    region_city: str = "",
    total_area_sqm: float = 0.0,
    price_per_sqm_egp: float = 0.0,
    total_price_egp: float = 0.0,
    status: str = "Available",
    usage_type: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> ERPSyncResult:
    """
    مزامنة بيانات الأرض مع ERP كمخزون (Product).

    في Odoo: ينشئ Product مع الخصائص المخصصة
    في SAP: ينشئ Material Master
    """
    payload = ERPLandPayload(
        land_id=land_id,
        owner_id=owner_id,
        owner_name=owner_name,
        governorate=governorate,
        region_city=region_city,
        total_area_sqm=total_area_sqm,
        price_per_sqm_egp=price_per_sqm_egp,
        total_price_egp=total_price_egp,
        status=status,
        usage_type=usage_type,
        latitude=latitude,
        longitude=longitude,
    )

    endpoints = {
        "odoo": "/api/product",
        "sap": "/api/material",
        "dynamics": "/api/inventory/item",
        "custom": "/api/lands",
    }
    endpoint = endpoints.get(ERP_SYSTEM, endpoints["custom"])

    result = await _call_erp(endpoint, asdict(payload), method="POST" if status == "Available" else "PUT")

    return ERPSyncResult(
        success=result.get("success", False),
        erp_reference=result.get("erp_reference", ""),
        message=result.get("message", ""),
        error=result.get("error"),
        synced_at=datetime.now(timezone.utc).isoformat(),
    )


# ──────────────────────────────────────────────
# 3. جلب حالة المخزون من ERP
# ──────────────────────────────────────────────

async def get_erp_inventory_status(
    land_id: Optional[str] = None,
    governorate: Optional[str] = None,
) -> Dict[str, Any]:
    """
    جلب حالة المخزون من ERP.

    Returns:
        dict مع المخزون الحالي (أو المصفى حسب land_id)
    """
    params = {}
    if land_id:
        params["land_id"] = land_id
    if governorate:
        params["governorate"] = governorate

    endpoints = {
        "odoo": "/api/product/stock",
        "sap": "/api/inventory",
        "dynamics": "/api/inventory/status",
        "custom": "/api/inventory",
    }
    endpoint = endpoints.get(ERP_SYSTEM, endpoints["custom"])

    result = await _call_erp(endpoint, params, method="GET")

    if not result.get("success"):
        return {"status": "error", "data": []}

    return {
        "status": "success",
        "data": result.get("data", []),
        "erp_reference": result.get("erp_reference", ""),
    }


# ──────────────────────────────────────────────
# 4. مزامنة عمولة الوسيط مع ERP
# ──────────────────────────────────────────────

async def sync_broker_commission(
    broker_id: str,
    broker_name: str = "",
    land_id: str = "",
    transaction_id: str = "",
    commission_amount_egp: float = 0.0,
    commission_pct: float = 0.0,
    is_winning_broker: bool = True,
) -> ERPSyncResult:
    """
    مزامنة عمولة الوسيط مع نظام ERP للحسابات.
    تُستخدم لدفع العمولات للوسطاء.
    """
    payload = {
        "broker_id": broker_id,
        "broker_name": broker_name,
        "land_id": land_id,
        "transaction_id": transaction_id,
        "commission_amount_egp": commission_amount_egp,
        "commission_pct": commission_pct,
        "is_winning_broker": is_winning_broker,
        "status": "Approved",
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    endpoints = {
        "odoo": "/api/commission/payment",
        "sap": "/api/vendor/payment",
        "dynamics": "/api/payables/commission",
        "custom": "/api/broker/commission",
    }
    endpoint = endpoints.get(ERP_SYSTEM, endpoints["custom"])

    result = await _call_erp(endpoint, payload)

    return ERPSyncResult(
        success=result.get("success", False),
        erp_reference=result.get("erp_reference", ""),
        message=result.get("message", ""),
        error=result.get("error"),
        synced_at=datetime.now(timezone.utc).isoformat(),
    )


# ──────────────────────────────────────────────
# 5. فحص صحة الاتصال بنظام ERP
# ──────────────────────────────────────────────

async def erp_health_check() -> Dict[str, Any]:
    """
    فحص صحة الاتصال بنظام ERP.

    Returns:
        dict مع حالة الاتصال
    """
    if not ERP_ENABLED:
        return {"status": "disabled", "system": ERP_SYSTEM, "message": "ERP integration is disabled"}

    if not ERP_API_URL:
        return {"status": "not_configured", "system": ERP_SYSTEM, "message": "ERP_API_URL not set"}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{ERP_API_URL.rstrip('/')}/api/health",
                headers=_build_headers(),
            )
            if response.status_code == 200:
                return {
                    "status": "connected",
                    "system": ERP_SYSTEM,
                    "url": ERP_API_URL,
                    "response": response.json(),
                }
            else:
                return {
                    "status": "error",
                    "system": ERP_SYSTEM,
                    "url": ERP_API_URL,
                    "http_status": response.status_code,
                }
    except ImportError:
        return {"status": "stub", "system": ERP_SYSTEM, "message": "httpx not installed — using stub"}
    except Exception as e:
        return {"status": "unreachable", "system": ERP_SYSTEM, "error": str(e)}


# ──────────────────────────────────────────────
# تشغيل مستقل للتجربة
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def test():
        print("=" * 60)
        print("  اختبار تكامل ERP")
        print("=" * 60)

        # اختبار 1: فحص الصحة
        print("\n1. فحص صحة ERP:")
        health = await erp_health_check()
        print(f"   {json.dumps(health, indent=2, ensure_ascii=False)}")

        # اختبار 2: مزامنة معاملة
        print("\n2. مزامنة معاملة:")
        result = await sync_transaction_to_erp(
            transaction_id="TX-TEST-001",
            land_id="LAND-CAI-001",
            buyer_id="INV-001",
            buyer_name="محمود حسن",
            seller_id="OWN-001",
            seller_name="أحمد علي",
            sale_price_egp=500_000.00,
            commission_egp=25_000.00,
            broker_id="BRK-001",
            broker_name="علي محمد",
            platform_fee_egp=2_500.00,
            net_to_seller_egp=472_500.00,
        )
        print(f"   Success: {result.success}")
        print(f"   ERP Ref: {result.erp_reference}")
        print(f"   Message: {result.message}")

        # اختبار 3: مزامنة أرض
        print("\n3. مزامنة أرض كمخزون:")
        result2 = await sync_land_to_erp(
            land_id="LAND-CAI-001",
            owner_id="OWN-001",
            owner_name="أحمد علي",
            governorate="القاهرة",
            region_city="التجمع الخامس",
            total_area_sqm=5000,
            price_per_sqm_egp=5000,
            total_price_egp=25_000_000,
            status="Available",
        )
        print(f"   Success: {result2.success}")
        print(f"   ERP Ref: {result2.erp_reference}")

        # اختبار 4: مزامنة عمولة وسيط
        print("\n4. مزامنة عمولة وسيط:")
        result3 = await sync_broker_commission(
            broker_id="BRK-001",
            broker_name="علي محمد",
            land_id="LAND-CAI-001",
            transaction_id="TX-TEST-001",
            commission_amount_egp=25_000.00,
            commission_pct=5.0,
        )
        print(f"   Success: {result3.success}")
        print(f"   ERP Ref: {result3.erp_reference}")

        print("\n✅ اختبار ERP مكتمل!")

    asyncio.run(test())