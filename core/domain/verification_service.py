"""
core.domain.verification_service
================================
خدمة التحقق من الأراضي — رفع الوثائق، تسجيل GPS، التحقق اليدوي.

المسؤوليات:
    1. upload_document: رفع وثيقة قانونية مع التحقق من الصيغة والحجم
    2. register_gps: تسجيل إحداثيات GPS مع التحقق من الملكية
    3. get_verification_status: استرجاع حالة التحقق الكاملة
    4. get_latest_gps: استرجاع آخر تسجيل GPS
    5. admin_manual_verify_location: تحقق يدوي (موافقة/رفض) من المسؤول

القواعد:
    - رفض الملفات بغير الصيغ: pdf, jpg, jpeg, png
    - حد أقصى للحجم: 10 ميغابايت
    - منع التكرار عبر SHA-256 hash
    - فقط مالك الأرض يرفع وثائق/يسجل GPS
    - الحالة تتحرك: pending → documents_uploaded → gps_registered → auto_verified → verified
                   أو → rejected (لو المسؤول رفض)
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.account.models import (
    DocumentType,
    GPSSource,
    LandDocument,
    LandGPSLog,
    LandVerificationStatus,
    OwnedLand,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# الثوابت
# ──────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 ميغابايت
UPLOAD_DIR = os.getenv("LAND_DOCS_UPLOAD_DIR", "/tmp/smart_land_docs")


# ──────────────────────────────────────────────
# LandVerificationService
# ──────────────────────────────────────────────

class LandVerificationService:
    """خدمة التحقق من الأراضي — تدير الوثائق و GPS وحالة التحقق."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ─── upload_document ───

    async def upload_document(
        self,
        land_id: str,
        document_type: str,
        file_content: bytes,
        original_filename: str,
        id_card_number: str = "",
        uploaded_by: str = "",
    ) -> Dict[str, Any]:
        """رفع وثيقة قانونية لأرض.

        Raises:
            ValueError: صيغة غير مدعومة / حجم كبير / مكرر / غير مالك
        """
        # 1) التحقق من الصيغة
        ext = os.path.splitext(original_filename.lower())[1]
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"صيغة الملف غير مدعومة: {ext}. المسموحة: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        # 2) التحقق من الحجم
        if len(file_content) > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"حجم الملف {len(file_content)} bytes يتجاوز 10 ميغابايت"
            )

        # 3) التحقق من الملكية
        land = await self._get_land(land_id)
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")
        if land.landowner_id != uploaded_by:
            raise ValueError("فقط مالك الأرض يمكنه رفع الوثائق")

        # 4) حساب SHA-256 hash
        file_hash = hashlib.sha256(file_content).hexdigest()

        # 5) فحص التكرار
        existing = await self._find_document_by_hash(land_id, file_hash)
        if existing:
            raise ValueError(f"الوثيقة مرفوعة مسبقاً (hash: {file_hash[:8]})")

        # 6) حفظ الملف فعلياً (لو نظام الملفات متاح)
        file_path = os.path.join(UPLOAD_DIR, f"{land_id}_{file_hash[:8]}{ext}")
        try:
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(file_content)
        except Exception as e:
            logger.warning("تعذّر حفظ الملف على القرص: %s — نُخزّن المسار فقط", e)
            file_path = f"/stored/{land_id}_{file_hash[:8]}{ext}"

        # 7) حفظ في DB
        doc = LandDocument(
            land_id=land_id,
            document_type=self._parse_document_type(document_type),
            file_path=file_path,
            file_hash=file_hash,
            file_size_kb=len(file_content) // 1024,
            original_filename=original_filename,
            id_card_number=id_card_number or None,
            uploaded_by=uploaded_by,
            verified_by_admin=False,
        )
        self.session.add(doc)

        # 8) تحديث حالة التحقق
        if land.verification_status == LandVerificationStatus.PENDING:
            land.verification_status = LandVerificationStatus.DOCUMENTS_UPLOADED

        await self.session.flush()
        await self.session.refresh(doc)

        logger.info(
            "تم رفع وثيقة: land=%s type=%s file=%s hash=%s",
            land_id, document_type, original_filename, file_hash[:8],
        )
        return doc.to_dict()

    # ─── register_gps ───

    async def register_gps(
        self,
        land_id: str,
        latitude: float,
        longitude: float,
        accuracy: Optional[float] = None,
        altitude: Optional[float] = None,
        source: str = "manual_entry",
        recorded_by: str = "",
    ) -> Dict[str, Any]:
        """تسجيل إحداثيات GPS لأرض.

        Raises:
            ValueError: غير مالك / أرض غير موجودة
        """
        # 1) التحقق من الملكية
        land = await self._get_land(land_id)
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")
        if land.landowner_id != recorded_by:
            raise ValueError("فقط مالك الأرض يمكنه تسجيل GPS")

        # 2) حفظ في DB
        # نضبط recorded_at صراحةً لضمان التفرد (server_default قد يرجع نفس القيمة في نفس الثانية)
        gps_log = LandGPSLog(
            land_id=land_id,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy,
            altitude_meters=altitude,
            source=self._parse_gps_source(source),
            recorded_by=recorded_by,
            is_verified=False,
            recorded_at=datetime.now(timezone.utc),
        )
        self.session.add(gps_log)

        # 3) تحديث حالة التحقق
        if land.verification_status in (
            LandVerificationStatus.PENDING,
            LandVerificationStatus.DOCUMENTS_UPLOADED,
        ):
            # لو عندنا وثائق + GPS، ننتقل لـ gps_registered أو auto_verified
            docs_count = await self._count_documents(land_id)
            if docs_count > 0:
                land.verification_status = LandVerificationStatus.AUTO_VERIFIED
            else:
                land.verification_status = LandVerificationStatus.GPS_REGISTERED

        await self.session.flush()
        await self.session.refresh(gps_log)

        logger.info(
            "تم تسجيل GPS: land=%s lat=%.4f lng=%.4f by=%s",
            land_id, latitude, longitude, recorded_by,
        )
        return gps_log.to_dict()

    # ─── get_latest_gps ───

    async def get_latest_gps(self, land_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع آخر تسجيل GPS لأرض.

        الترتيب: recorded_at DESC ثم id DESC (لتفادي التضارب لو نفس الطابع الزمني).
        """
        stmt = (
            select(LandGPSLog)
            .where(LandGPSLog.land_id == land_id)
            .order_by(LandGPSLog.recorded_at.desc(), LandGPSLog.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        gps = result.scalar_one_or_none()
        return gps.to_dict() if gps else None

    # ─── get_verification_status ───

    async def get_verification_status(self, land_id: str) -> Dict[str, Any]:
        """استرجاع حالة التحقق الكاملة لأرض."""
        land = await self._get_land(land_id)
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")

        documents = await self._list_documents(land_id)
        latest_gps = await self.get_latest_gps(land_id)

        # حساب الوثائق المفقودة
        uploaded_types = {d.get("document_type") for d in documents}
        required_types = {"title_deed", "id_card"}  # الحد الأدنى المطلوب
        missing_types = list(required_types - uploaded_types)

        return {
            "land_id": land_id,
            "verification_status": land.verification_status.value if land.verification_status else "pending",
            "documents_count": len(documents),
            "documents": documents,
            "gps_registered": latest_gps is not None,
            "latest_gps": latest_gps,
            "verified_by_admin": any(d.get("verified_by_admin") for d in documents),
            "missing_document_types": missing_types,
        }

    # ─── admin_manual_verify_location ───

    async def admin_manual_verify_location(
        self,
        land_id: str,
        admin_id: str,
        approved: bool,
        notes: str = "",
    ) -> Dict[str, Any]:
        """تحقق يدوي من المسؤول — موافقة أو رفض.

        Args:
            land_id: معرف الأرض
            admin_id: معرف المسؤول
            approved: True للموافقة، False للرفض
            notes: ملاحظات المسؤول

        Returns:
            dict: {approved, status, land_id, admin_id, notes}
        """
        land = await self._get_land(land_id)
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")

        if approved:
            land.verification_status = LandVerificationStatus.VERIFIED
            status = "verified"
        else:
            land.verification_status = LandVerificationStatus.REJECTED
            status = "rejected"

        # تعليم جميع الوثائق بأنها تم فحصها من المسؤول — تحديث جماعي
        # (تجنّب المرور على id الفردي لأنه UUID قد يسبب مشاكل في SQLite)
        from sqlalchemy import update as sql_update
        stmt = (
            sql_update(LandDocument)
            .where(LandDocument.land_id == land_id)
            .values(
                verified_by_admin=True,
                verified_by_admin_id=admin_id,
                verified_at=datetime.now(timezone.utc),
                admin_notes=notes,
            )
        )
        await self.session.execute(stmt)

        await self.session.flush()

        logger.info(
            "تحقق يدوي: land=%s approved=%s admin=%s notes=%s",
            land_id, approved, admin_id, notes,
        )
        return {
            "approved": approved,
            "status": status,
            "land_id": land_id,
            "admin_id": admin_id,
            "notes": notes,
        }

    # ─── helpers ───

    async def _get_land(self, land_id: str) -> Optional[OwnedLand]:
        stmt = select(OwnedLand).where(OwnedLand.land_id == land_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_document_by_hash(self, land_id: str, file_hash: str) -> Optional[LandDocument]:
        stmt = (
            select(LandDocument)
            .where(LandDocument.land_id == land_id)
            .where(LandDocument.file_hash == file_hash)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _count_documents(self, land_id: str) -> int:
        from sqlalchemy import func
        stmt = (
            select(func.count())
            .select_from(LandDocument)
            .where(LandDocument.land_id == land_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _list_documents(self, land_id: str) -> List[Dict[str, Any]]:
        stmt = (
            select(LandDocument)
            .where(LandDocument.land_id == land_id)
            .order_by(LandDocument.uploaded_at.desc())
        )
        result = await self.session.execute(stmt)
        return [d.to_dict() for d in result.scalars().all()]

    @staticmethod
    def _parse_document_type(value: str) -> DocumentType:
        """يحوّل نص إلى DocumentType enum."""
        try:
            return DocumentType(value)
        except ValueError:
            # محاولة بإضافة underscores أو تطبيع
            normalized = value.lower().replace("-", "_").replace(" ", "_")
            for t in DocumentType:
                if t.value == normalized or t.value == value:
                    return t
            return DocumentType.OTHER

    @staticmethod
    def _parse_gps_source(value: str) -> GPSSource:
        """يحوّل نص إلى GPSSource enum."""
        try:
            return GPSSource(value)
        except ValueError:
            normalized = value.lower().replace("-", "_").replace(" ", "_")
            for s in GPSSource:
                if s.value == normalized or s.value == value:
                    return s
            return GPSSource.MANUAL_ENTRY


__all__ = ["LandVerificationService"]
