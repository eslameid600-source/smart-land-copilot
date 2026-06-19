"""
نقاط نهاية API للتحقق من الأراضي
=====================================
المسارات:
    POST   /api/lands/{land_id}/upload-document  – رفع وثيقة قانونية
    POST   /api/lands/{land_id}/register-gps      – تسجيل إحداثيات GPS
    GET    /api/lands/{land_id}/verification-status – حالة التحقق
    POST   /api/lands/{land_id}/verify-location   – تحقق يدوي (للمسؤول)
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.database import get_db
from core.domain.verification_service import LandVerificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Land Verification"])


def get_verification_service(session: AsyncSession = Depends(get_db)) -> LandVerificationService:
    return LandVerificationService(session)


# ──────────────────────────────────────────
# رفع وثيقة قانونية
# ──────────────────────────────────────────

@router.post("/lands/{land_id}/upload-document")
async def upload_document(
    land_id: str,
    document_type: str = Form(...),
    id_card_number: str = Form(""),
    uploaded_by: str = Form(""),
    file: UploadFile = File(...),
    service: LandVerificationService = Depends(get_verification_service),
):
    """
    رفع وثيقة قانونية لأرض.

    - **document_type**: title_deed, contract, tax_receipt, id_card, commercial_register, other
    - **id_card_number**: رقم البطاقة الشخصية أو السجل التجاري
    - **file**: الملف (PDF, JPG, PNG)
    """
    try:
        content = await file.read()
        result = await service.upload_document(
            land_id=land_id,
            document_type=document_type,
            file_content=content,
            original_filename=file.filename,
            id_card_number=id_card_number,
            uploaded_by=uploaded_by,
        )
        return {"success": True, "document": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"خطأ في رفع الوثيقة: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")


# ──────────────────────────────────────────
# تسجيل GPS
# ──────────────────────────────────────────

@router.post("/lands/{land_id}/register-gps")
async def register_gps(
    land_id: str,
    latitude: float,
    longitude: float,
    accuracy: float = None,
    altitude: float = None,
    source: str = "manual_entry",
    recorded_by: str = "",
    service: LandVerificationService = Depends(get_verification_service),
):
    """
    تسجيل إحداثيات GPS للأرض.

    - **latitude**: خط العرض
    - **longitude**: خط الطول
    - **accuracy**: دقة الإحداثيات بالمتر (اختياري)
    - **source**: browser_geolocation, mobile_app, manual_entry, admin_verified
    """
    try:
        result = await service.register_gps(
            land_id=land_id,
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy,
            altitude=altitude,
            source=source,
            recorded_by=recorded_by,
        )
        return {"success": True, "gps_log": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"خطأ في تسجيل GPS: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")


# ──────────────────────────────────────────
# حالة التحقق
# ──────────────────────────────────────────

@router.get("/lands/{land_id}/verification-status")
async def get_verification_status(
    land_id: str,
    service: LandVerificationService = Depends(get_verification_service),
):
    """عرض حالة التحقق الكاملة لأرض."""
    try:
        status_data = await service.get_verification_status(land_id)
        return {"success": True, "status": status_data}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"خطأ في جلب حالة التحقق: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")


# ──────────────────────────────────────────
# تحقق يدوي (للمسؤول)
# ──────────────────────────────────────────

@router.post("/lands/{land_id}/verify-location")
async def admin_verify_location(
    land_id: str,
    admin_id: str,
    approved: bool = True,
    notes: str = "",
    service: LandVerificationService = Depends(get_verification_service),
):
    """
    تحقق يدوي من تطابق الموقع مع الوثائق.

    - **admin_id**: معرّف المسؤول
    - **approved**: true للموافقة، false للرفض
    - **notes**: ملاحظات
    """
    try:
        result = await service.admin_manual_verify_location(
            land_id=land_id,
            admin_id=admin_id,
            approved=approved,
            notes=notes,
        )
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"خطأ في التحقق اليدوي: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ في الخادم")