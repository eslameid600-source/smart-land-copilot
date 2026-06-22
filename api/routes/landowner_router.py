"""
مسارات ملاك الأراضي — LandownerRouter
=======================================
POST   /landowners                   → إنشاء حساب مالك
GET    /landowners                   → قائمة الملاك
GET    /landowners/{id}              → بيانات مالك
GET    /landowners/{id}/lands        → أراضي المالك
PUT    /landowners/{id}/commission   → تحديث عمولة
POST   /landowners/{id}/list-land    → إعلان أرض
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from api.routes._deps import get_landowner_store
from core.domain.entities import APIResponse, LandownerCreateRequest

router = APIRouter(prefix="/api/v1", tags=["landowners"])


@router.post("/landowners", response_model=APIResponse, status_code=201)
async def create_landowner(req: LandownerCreateRequest):
    """
    إنشاء حساب مالك أرض جديد.

    - **user_id**: معرّف المستخدم من خدمة المصادقة
    - **default_commission_pct**: نسبة العمولة الافتراضية (0-50%)
    """
    store = get_landowner_store()
    try:
        landowner = store.create(
            user_id=req.user_id,
            default_commission_pct=req.default_commission_pct,
        )
        return APIResponse(
            data=landowner,
            message=f"تم إنشاء حساب مالك الأرض {req.user_id} بنجاح",
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/landowners", response_model=APIResponse)
async def list_landowners(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """قائمة جميع ملاك الأراضي."""
    store = get_landowner_store()
    all_owners = store.get_all()

    total = len(all_owners)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    page_data = all_owners[start : start + per_page]

    return APIResponse(
        data=page_data,
        meta={"total": total, "page": page, "per_page": per_page, "total_pages": total_pages},
        message=f"قائمة ملاك الأراضي ({total} مالك)",
    )


@router.get("/landowners/{user_id}", response_model=APIResponse)
async def get_landowner(user_id: str):
    """استرجاع بيانات مالك أرض واحد."""
    store = get_landowner_store()
    landowner = store.get(user_id)
    if not landowner:
        raise HTTPException(status_code=404, detail=f"مالك الأرض {user_id} غير موجود")
    return APIResponse(data=landowner, message="تم استرجاع بيانات مالك الأرض")


@router.get("/landowners/{user_id}/lands", response_model=APIResponse)
async def get_landowner_lands(
    user_id: str,
    status: Optional[str] = Query(None, description="فلتر: متاح / مباع / مزاد"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    استرجاع الأراضي المملوكة لمالك محدد.

    يعرض تفاصيل كل أرض: الاسم، المحافظة، المساحة، السعر، الجودة،
    حالة الاستثمار، عدد المشاهدات والاستفسارات.
    """
    store = get_landowner_store()

    if not store.exists(user_id):
        raise HTTPException(status_code=404, detail=f"مالك الأرض {user_id} غير موجود")

    lands = store.get_lands(user_id, status=status, limit=limit)

    return APIResponse(
        data=lands,
        meta={
            "user_id": user_id,
            "total_lands_returned": len(lands),
            "status_filter": status,
        },
        message=f"أراضي المالك ({len(lands)} أرض)",
    )


@router.put("/landowners/{user_id}/commission", response_model=APIResponse)
async def update_landowner_commission(
    user_id: str,
    commission_pct: float = Query(..., ge=0, le=50, description="النسبة الجديدة (0-50%)"),
):
    """تحديث نسبة العمولة الافتراضية لمالك الأرض."""
    store = get_landowner_store()

    if not store.exists(user_id):
        raise HTTPException(status_code=404, detail=f"مالك الأرض {user_id} غير موجود")

    try:
        updated = store.update_commission(user_id, commission_pct)
        return APIResponse(
            data=updated,
            message=f"تم تحديث نسبة العمولة إلى {commission_pct}%",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/landowners/{user_id}/list-land", response_model=APIResponse, status_code=201)
async def list_new_land(user_id: str, request: Request):
    """
    إعلان أرض جديدة لملك محدد.

    يُرسل بيانات الأرض في body الطلب (JSON).
    الحقول المطلوبة: land_id, name, governorate, activity, area_sqm,
                     price_per_sqm_egp, total_price_egp.
    الحقول الاختيارية: quality, latitude, longitude, description, investment_status.
    """
    store = get_landowner_store()

    if not store.exists(user_id):
        raise HTTPException(status_code=404, detail=f"مالك الأرض {user_id} غير موجود")

    land_data = await request.json()
    land_data.setdefault("quality", "B")
    land_data.setdefault("investment_status", "متاح")

    # التحقق من الحقول المطلوبة
    required_fields = ["land_id", "name", "governorate", "activity", "area_sqm", "price_per_sqm_egp", "total_price_egp"]
    missing = [f for f in required_fields if f not in land_data or not land_data[f]]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"حقول مطلوبة مفقودة: {', '.join(missing)}",
        )

    try:
        land_record = store.list_land(user_id, land_data)
        return APIResponse(
            data=land_record,
            message=f"تم إعلان الأرض {land_data['land_id']} بنجاح",
            status_code=201,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
