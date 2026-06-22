"""
نقاط نهاية API للوسطاء
=========================
المسارات:
    POST   /api/brokers/register          – تسجيل وسيط جديد
    GET    /api/brokers/community         – قائمة الوسطاء النشطين (مع بحث)
    GET    /api/brokers/{broker_id}       – ملف الوسيط
    GET    /api/brokers/{broker_id}/lands – الأراضي التي يديرها
    GET    /api/brokers/{broker_id}/earnings – الأرباح
    POST   /api/lands/{land_id}/assign-broker – تعيين وسيط لأرض
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.account.broker_repository import BrokerRepository
from core.account.broker_service import BrokerService
from infrastructure.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Brokers"])


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

def get_broker_service(session: AsyncSession = Depends(get_db)) -> BrokerService:
    return BrokerService(session)


def get_broker_repo(session: AsyncSession = Depends(get_db)) -> BrokerRepository:
    return BrokerRepository(session)


# ──────────────────────────────────────────
# تسجيل وسيط جديد
# ──────────────────────────────────────────

@router.post("/brokers/register")
async def register_broker(
    user_id: str,
    full_name: str,
    phone_number: str = "",
    email: str = "",
    default_commission_rate: float = 2.5,
    specialization: str = "",
    bio: str = "",
    service: BrokerService = Depends(get_broker_service),
):
    """
    تسجيل وسيط جديد في المنصة.

    - **user_id**: معرّف المستخدم (يجب أن يكون دوره Certified Broker)
    - **full_name**: اسم الوسيط الكامل
    - **default_commission_rate**: نسبة العمولة الافتراضية (1% إلى 20%)
    """
    try:
        spec_list = [s.strip() for s in specialization.split(",") if s.strip()] if specialization else []
        result = await service.register_broker(
            user_id=user_id,
            full_name=full_name,
            phone_number=phone_number,
            email=email,
            default_commission_rate=default_commission_rate,
            specialization=spec_list,
            bio=bio,
        )
        return {"success": True, "broker": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"خطأ في تسجيل الوسيط: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")


# ──────────────────────────────────────────
# قائمة مجتمع الوسطاء (للبحث)
# ──────────────────────────────────────────

@router.get("/brokers/community")
async def get_broker_community(
    query: str = Query("", description="البحث بالاسم أو الكود"),
    specialization: str = Query("", description="التخصص للبحث"),
    limit: int = Query(50, ge=1, le=100),
    service: BrokerService = Depends(get_broker_service),
):
    """
    عرض قائمة الوسطاء النشطين مع إمكانية البحث.

    مثال:
        GET /api/brokers/community?query=أحمد&specialization=سكني&limit=20
    """
    try:
        spec = specialization if specialization else None
        brokers = await service.list_broker_community(query=query, specialization=spec, limit=limit)
        return {"success": True, "brokers": brokers, "count": len(brokers)}
    except Exception as e:
        logger.error(f"خطأ في جلب مجتمع الوسطاء: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")


# ──────────────────────────────────────────
# ملف الوسيط
# ──────────────────────────────────────────

@router.get("/brokers/{broker_id}")
async def get_broker_profile(
    broker_id: str,
    service: BrokerService = Depends(get_broker_service),
):
    """استرجاع ملف الوسيط الكامل مع إحصائياته."""
    try:
        profile = await service.get_broker_profile(broker_id)
        if not profile:
            raise HTTPException(status_code=404, detail="الوسيط غير موجود")
        return {"success": True, "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"خطأ في جلب ملف الوسيط: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")


# ──────────────────────────────────────────
# الأراضي التي يديرها الوسيط
# ──────────────────────────────────────────

@router.get("/brokers/{broker_id}/lands")
async def get_broker_lands(
    broker_id: str,
    service: BrokerService = Depends(get_broker_service),
):
    """عرض الأراضي المعينة لهذا الوسيط."""
    try:
        lands = await service.list_broker_lands(broker_id)
        return {"success": True, "lands": lands, "count": len(lands)}
    except Exception as e:
        logger.error(f"خطأ في جلب أراضي الوسيط: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")


# ──────────────────────────────────────────
# أرباح الوسيط
# ──────────────────────────────────────────

@router.get("/brokers/{broker_id}/earnings")
async def get_broker_earnings(
    broker_id: str,
    repo: BrokerRepository = Depends(get_broker_repo),
):
    """حساب إجمالي أرباح الوسيط (مستحقة + مدفوعة)."""
    try:
        earnings = await repo.get_broker_earnings(broker_id)
        return {"success": True, "earnings": earnings}
    except Exception as e:
        logger.error(f"خطأ في جلب أرباح الوسيط: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")


# ──────────────────────────────────────────
# تعيين وسيط لأرض
# ──────────────────────────────────────────

@router.post("/lands/{land_id}/assign-broker")
async def assign_broker_to_land(
    land_id: str,
    broker_id: str,
    commission_percent: Optional[float] = None,
    requesting_user_id: Optional[str] = None,
    service: BrokerService = Depends(get_broker_service),
):
    """
    تعيين وسيط لأرض معينة.

    - **land_id**: معرّف الأرض
    - **broker_id**: معرّف الوسيط
    - **commission_percent**: نسبة العمولة (اختياري)
    - **requesting_user_id**: المستخدم الذي يطلب التعيين (للتحقق من الصلاحية)

    ملاحظة: فقط مالك الأرض يمكنه تعيين وسيط.
    """
    try:
        commission = commission_percent if commission_percent is not None else None
        result = await service.assign_broker_to_land(
            land_id=land_id,
            broker_id=broker_id,
            commission_percent=commission,
            requesting_user_id=requesting_user_id,
        )
        return {"success": True, "assignment": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"خطأ في تعيين الوسيط: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")


# ──────────────────────────────────────────
# إحصائيات الوسطاء
# ──────────────────────────────────────────

@router.get("/brokers/stats/overview")
async def get_brokers_overview(
    service: BrokerService = Depends(get_broker_service),
):
    """إحصائيات عامة عن مجتمع الوسطاء."""
    try:
        stats = await service.get_broker_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"خطأ في جلب إحصائيات الوسطاء: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")