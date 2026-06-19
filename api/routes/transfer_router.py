"""
مسار نقل الملكية — TransferRouter
====================================
POST   /transfer-ownership → نقل ملكية أرض
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from core.domain.entities import OwnershipTransferRequest, OwnershipTransferResult
from core.account.store import transfer_ownership
from api.routes._deps import get_stores, lands_catalog_global

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["transfer"])


@router.post("/transfer-ownership", response_model=OwnershipTransferResult)
async def handle_transfer_ownership(req: OwnershipTransferRequest):
    """
    نقل ملكية أرض عند اكتمال عملية الشراء.

    تنفذ الدالة الخطوات التالية:
        1. التحقق من الأرض (موجودة + متاحة)
        2. التحقق من المشتري (مسجل + رصيد كافٍ)
        3. حساب السعر والعمولات
        4. خصم من محفظة المشتري
        5. تحديث حالة الأرض → مباع
        6. تحديث إحصائيات المشتري والبائع
        7. إضافة نقاط ولاء
        8. إزالة الأرض من قائمة البائع

    - **land_id**: معرّف الأرض
    - **buyer_id**: معرّف المشتري (المستثمر)
    - **commission_pct**: نسبة العمولة (اختياري — تُستخدم نسبة المالك الافتراضية)
    - **payment_gateway**: بوابة الدفع (wallet / fawry / stripe)
    """
    inv_store, lo_store = get_stores()

    # إذا الأرض ليست في الكتالوج المحلي → حاول جلبها
    if req.land_id not in lands_catalog_global:
        land = _try_fetch_land(req.land_id)
        if land:
            lands_catalog_global[req.land_id] = land

    try:
        result = transfer_ownership(
            land_id=req.land_id,
            buyer_id=req.buyer_id,
            investor_store=inv_store,
            landowner_store=lo_store,
            commission_pct=req.commission_pct,
        )

        return OwnershipTransferResult(
            success=result["success"],
            land_id=result["land_id"],
            seller_id=result["seller_id"],
            buyer_id=result["buyer_id"],
            sale_price_egp=result["sale_price_egp"],
            commission_egp=result["commission_egp"],
            loyalty_points_earned=result["loyalty_points_earned"],
            new_owner_id=result["new_owner_id"],
            transaction_id=result["transaction_id"],
            transferred_at=result["transferred_at"],
            message_ar=result["message_ar"],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"خطأ في نقل الملكية: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطأ داخلي في نقل الملكية: {str(e)}")


# ──────────────────────────────────────────────
# Helper: محاولة جلب أرض من خدمة الأراضي
# ──────────────────────────────────────────────

def _try_fetch_land(land_id: str) -> Optional[dict]:
    """
    محاولة جلب بيانات أرض من خدمة الأراضي (land-service)
    عبر HTTP داخلي أو من البيانات المحلية.
    """
    import json

    # محاولة 1: قراءة من ملف البيانات المحلية
    try:
        from core.domain.land_database import get_all_lands
        for land in get_all_lands():
            if land.get("land_id") == land_id:
                land_copy = dict(land)
                if "owner_id" not in land_copy:
                    land_copy["owner_id"] = f"owner-{land_id}"
                return land_copy
    except ImportError:
        pass

    # محاولة 2: HTTP call to land-service (internal)
    try:
        import httpx
        resp = httpx.get(
            f"http://land-service:8002/api/lands/{land_id}",
            timeout=3.0,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            if "owner_id" not in data:
                data["owner_id"] = f"owner-{land_id}"
            return data
    except Exception:
        pass

    return None
