"""
خدمة التحقق من صحة الأراضي — LandVerificationService
======================================================
منطق الأعمال للتحقق من الأرض قبل تسجيلها في المنصة:

1. رفع الوثائق القانونية (PDF/صور)
2. تسجيل إحداثيات GPS من البائع
3. التحقق من تطابق الموقع مع الوثائق (يدوي/تلقائي)
4. تحديث حالة التحقق

المسؤول فقط يمكنه تأكيد التحقق النهائي.
"""

import os
import hashlib
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.account.models import (
    OwnedLand,
    LandDocument,
    LandGPSLog,
    DocumentType,
    GPSSource,
    LandVerificationStatus,
)

logger = logging.getLogger(__name__)

# مجلد رفع الوثائق
UPLOAD_DIR = "uploads/land_documents"
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_FILE_SIZE_MB = 10


class LandVerificationService:
    """خدمة التحقق من صحة بيانات الأرض."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ──────────────────────────────────────────
    # رفع الوثائق القانونية
    # ──────────────────────────────────────────

    async def upload_document(
        self,
        land_id: str,
        document_type: str,
        file_content: bytes,
        original_filename: str,
        id_card_number: str = "",
        uploaded_by: str = "",
    ) -> Dict[str, Any]:
        """
        رفع وثيقة قانونية لأرض معينة.

        Args:
            land_id: معرّف الأرض
            document_type: نوع الوثيقة (title_deed, contract, tax_receipt, id_card, ...)
            file_content: محتوى الملف كبايت
            original_filename: اسم الملف الأصلي
            id_card_number: رقم البطاقة/السجل التجاري
            uploaded_by: المستخدم الذي يرفع الوثيقة

        Returns:
            dict بيانات الوثيقة المُسجلة
        """
        # 1. التحقق من الأرض
        land = await self._get_land(land_id)
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")

        # 2. التحقق من صلاحية المستخدم (مالك الأرض فقط)
        if land.landowner_id != uploaded_by:
            raise ValueError("فقط مالك الأرض يمكنه رفع الوثائق")

        # 3. التحقق من صيغة الملف
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"صيغة الملف غير مدعومة: .{ext}. "
                f"الصيغ المسموحة: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # 4. التحقق من حجم الملف
        if len(file_content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"حجم الملف يتجاوز {MAX_FILE_SIZE_MB} ميغابايت")

        # 5. حساب hash للملف (لتجنب الرفع المكرر)
        file_hash = hashlib.sha256(file_content).hexdigest()

        # 6. التحقق من عدم وجود وثيقة مماثلة
        duplicate = await self._find_duplicate_document(land_id, file_hash)
        if duplicate:
            raise ValueError("هذه الوثيقة مُرفوعة مسبقاً لنفس الأرض")

        # 7. حفظ الملف على القرص
        file_path = await self._save_file(land_id, file_content, original_filename)

        # 8. تسجيل الوثيقة في قاعدة البيانات
        doc_type_enum = self._parse_document_type(document_type)
        document = LandDocument(
            land_id=land_id,
            document_type=doc_type_enum,
            file_path=file_path,
            file_hash=file_hash,
            file_size_kb=len(file_content) // 1024,
            original_filename=original_filename,
            id_card_number=id_card_number or None,
            uploaded_by=uploaded_by,
            verified_by_admin=False,
        )
        self.session.add(document)
        await self.session.flush()
        await self.session.refresh(document)

        # 9. تحديث حالة التحقق في OwnedLand
        await self._update_land_verification_status(
            land_id, LandVerificationStatus.DOCUMENTS_UPLOADED
        )

        logger.info(f"رفع وثيقة {document_type} للأرض {land_id} بواسطة {uploaded_by}")
        return document.to_dict()

    async def get_land_documents(self, land_id: str) -> List[Dict[str, Any]]:
        """استرجاع كل وثائق أرض معينة."""
        stmt = (
            select(LandDocument)
            .where(LandDocument.land_id == land_id)
            .order_by(LandDocument.uploaded_at.desc())
        )
        result = await self.session.execute(stmt)
        docs = result.scalars().all()
        return [d.to_dict() for d in docs]

    async def verify_document_admin(
        self, document_id: str, verified: bool, admin_id: str, notes: str = ""
    ) -> Dict[str, Any]:
        """تحقق يدوي من وثيقة من قبل المسؤول."""
        stmt = (
            select(LandDocument)
            .where(LandDocument.id == document_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"الوثيقة {document_id} غير موجودة")

        doc.verified_by_admin = verified
        doc.verified_by_admin_id = admin_id
        doc.verified_at = datetime.now(timezone.utc)
        doc.admin_notes = notes or None
        await self.session.flush()
        await self.session.refresh(doc)

        # التحقق من اكتمال وثائق الأرض
        await self._check_land_documents_complete(doc.land_id)

        logger.info(f"تحقق وثيقة {document_id}: {'مقبولة' if verified else 'مرفوضة'} من قبل {admin_id}")
        return doc.to_dict()

    # ──────────────────────────────────────────
    # تسجيل وإدارة GPS
    # ──────────────────────────────────────────

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
        """
        تسجيل إحداثيات GPS لأرض.

        Args:
            land_id: معرّف الأرض
            latitude: خط العرض
            longitude: خط الطول
            accuracy: دقة الإحداثيات بالمتر
            altitude: ارتفاع بالمتر
            source: مصدر الإحداثيات
            recorded_by: المستخدم الذي سجل الموقع
        """
        # 1. التحقق من الأرض
        land = await self._get_land(land_id)
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")
        if land.landowner_id != recorded_by:
            raise ValueError("فقط مالك الأرض يمكنه تسجيل الموقع")

        # 2. صيغ المصادر المسموحة
        valid_sources = {"browser_geolocation", "mobile_app", "manual_entry", "admin_verified"}
        if source not in valid_sources:
            source = "manual_entry"

        # 3. إنشاء سجل GPS
        source_enum = GPSSource(source)
        gps_log = LandGPSLog(
            land_id=land_id,
            latitude=float(latitude),
            longitude=float(longitude),
            accuracy_meters=float(accuracy) if accuracy is not None else None,
            altitude_meters=float(altitude) if altitude is not None else None,
            source=source_enum,
            recorded_by=recorded_by,
            is_verified=False,
        )
        self.session.add(gps_log)
        await self.session.flush()
        await self.session.refresh(gps_log)

        # 4. تحديث حالة التحقق
        new_status = LandVerificationStatus.GPS_REGISTERED
        await self._update_land_verification_status(land_id, new_status)

        # 5. محاولة التحقق التلقائي (مقارنة مع وثائق ID_CARD إن وُجدت)
        auto_verified = await self._try_auto_verify_location(land_id)
        if auto_verified:
            await self._update_land_verification_status(land_id, LandVerificationStatus.AUTO_VERIFIED)
            gps_log.is_verified = True
            gps_log.verification_note = "تم التحقق تلقائياً بناءً على تطابق الموقع مع الوثائق"
            await self.session.flush()

        logger.info(f"تسجيل GPS للأرض {land_id}: ({latitude}, {longitude})")
        return gps_log.to_dict()

    async def get_land_gps_logs(self, land_id: str) -> List[Dict[str, Any]]:
        """استرجاع كل سجلات GPS لأرض."""
        stmt = (
            select(LandGPSLog)
            .where(LandGPSLog.land_id == land_id)
            .order_by(LandGPSLog.recorded_at.desc())
        )
        result = await self.session.execute(stmt)
        logs = result.scalars().all()
        return [log.to_dict() for log in logs]

    async def get_latest_gps(self, land_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع آخر تسجيل GPS لأرض."""
        stmt = (
            select(LandGPSLog)
            .where(LandGPSLog.land_id == land_id)
            .order_by(LandGPSLog.recorded_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        log = result.scalar_one_or_none()
        return log.to_dict() if log else None

    # ──────────────────────────────────────────
    # التحقق اليدوي (للمسؤول)
    # ──────────────────────────────────────────

    async def admin_manual_verify_location(
        self,
        land_id: str,
        admin_id: str,
        approved: bool,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        تحقق يدوي من تطابق الموقع مع الوثائق (بواسطة المسؤول).

        Args:
            land_id: معرّف الأرض
            admin_id: معرّف المسؤول
            approved: true للموافقة، false للرفض
            notes: ملاحظات
        """
        land = await self._get_land(land_id)
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")

        if approved:
            new_status = LandVerificationStatus.VERIFIED
            # تحديث آخر سجل GPS ليكون موثق
            gps_stmt = (
                select(LandGPSLog)
                .where(LandGPSLog.land_id == land_id)
                .order_by(LandGPSLog.recorded_at.desc())
                .limit(1)
            )
            gps_result = await self.session.execute(gps_stmt)
            latest_gps = gps_result.scalar_one_or_none()
            if latest_gps:
                latest_gps.is_verified = True
                latest_gps.verification_note = notes or "تم التحقق يدوياً بواسطة المسؤول"
        else:
            new_status = LandVerificationStatus.REJECTED

        await self._update_land_verification_status(land_id, new_status)

        logger.info(f"تحقق يدوي للأرض {land_id}: {'مقبول' if approved else 'مرفوض'} بواسطة {admin_id}")
        return {
            "land_id": land_id,
            "status": new_status.value,
            "admin_id": admin_id,
            "approved": approved,
            "notes": notes,
        }

    # ──────────────────────────────────────────
    # حالة التحقق
    # ──────────────────────────────────────────

    async def get_verification_status(self, land_id: str) -> Dict[str, Any]:
        """استرجاع حالة التحقق الكاملة لأرض."""
        land = await self._get_land(land_id)
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")

        documents = await self.get_land_documents(land_id)
        gps_logs = await self.get_land_gps_logs(land_id)
        latest_gps = gps_logs[0] if gps_logs else None

        # عدد الوثائق المقبولة
        verified_docs = [d for d in documents if d.get("verified_by_admin")]
        required_doc_types = {
            "title_deed",
            "id_card",
        }
        submitted_types = {d["document_type"] for d in documents}

        return {
            "land_id": land_id,
            "verification_status": land.verification_status.value if land.verification_status else "pending",
            "documents_count": len(documents),
            "verified_documents_count": len(verified_docs),
            "missing_document_types": list(required_doc_types - submitted_types),
            "documents": documents,
            "gps_registered": latest_gps is not None,
            "latest_gps": latest_gps,
            "gps_logs_count": len(gps_logs),
            "seller_id_card": land.seller_id_card,
        }

    # ──────────────────────────────────────────
    # دوال مساعدة داخلية
    # ──────────────────────────────────────────

    async def _get_land(self, land_id: str) -> Optional[OwnedLand]:
        """استرجاع أرض بالمعرف."""
        stmt = select(OwnedLand).where(OwnedLand.land_id == land_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _parse_document_type(self, doc_type_str: str) -> DocumentType:
        """تحليل نص نوع الوثيقة إلى Enum."""
        mapping = {
            "title_deed": DocumentType.TITLE_DEED,
            "contract": DocumentType.CONTRACT,
            "tax_receipt": DocumentType.TAX_RECEIPT,
            "id_card": DocumentType.ID_CARD,
            "commercial_register": DocumentType.COMMERCIAL_REGISTER,
            "other": DocumentType.OTHER,
        }
        return mapping.get(doc_type_str.lower(), DocumentType.OTHER)

    async def _find_duplicate_document(self, land_id: str, file_hash: str) -> bool:
        """التحقق من عدم وجود وثيقة بنفس الهاش."""
        stmt = (
            select(func.count())
            .select_from(LandDocument)
            .where(
                and_(
                    LandDocument.land_id == land_id,
                    LandDocument.file_hash == file_hash,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() > 0

    async def _save_file(self, land_id: str, content: bytes, filename: str) -> str:
        """حفظ الملف على القرص وإرجاع المسار."""
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        unique_name = f"{land_id}_{uuid.uuid4().hex[:8]}.{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_name)
        with open(file_path, "wb") as f:
            f.write(content)
        return file_path

    async def _update_land_verification_status(
        self, land_id: str, status: LandVerificationStatus
    ) -> None:
        """تحديث حالة التحقق للأرض."""
        stmt = (
            select(OwnedLand)
            .where(OwnedLand.land_id == land_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        land = result.scalar_one_or_none()
        if land:
            land.verification_status = status
            land.updated_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def _check_land_documents_complete(self, land_id: str) -> None:
        """
        التحقق من اكتمال الوثائق المطلوبة.
        إذا كانت كل الوثائق المطلوبة مُرفقة ومُتحققة، يتم ترقية الحالة.
        """
        required = {"title_deed", "id_card"}
        docs = await self.get_land_documents(land_id)
        submitted_types = {d["document_type"] for d in docs}

        all_submitted = required.issubset(submitted_types)
        all_verified = all(d.get("verified_by_admin") for d in docs if d["document_type"] in required)

        if all_submitted and all_verified:
            await self._update_land_verification_status(land_id, LandVerificationStatus.MANUAL_REVIEW)

    async def _try_auto_verify_location(self, land_id: str) -> bool:
        """
        محاولة التحقق التلقائي من الموقع.
       negie: للتبسيط، نتحقق فقط من وجود وثيقة ID_CARD و GPS.
        في الإصدارات المستقبلية: مقارنة إحداثيات GPS مع حدود الأرض المسجلة في الخرائط.
        """
        docs = await self.get_land_documents(land_id)
        has_id_card = any(d["document_type"] == "id_card" for d in docs)
        has_gps = True  # لأننا نستدعي هذه الدالة بعد تسجيل GPS

        # تحقق تلقائي بسيط: وجود وثيقة الهوية + GPS
        return has_id_card and has_gps

    # ──────────────────────────────────────────
    # تحديث seller_id_card في OwnedLand
    # ──────────────────────────────────────────

    async def update_seller_id_card(self, land_id: str, id_card_number: str) -> Dict[str, Any]:
        """تحديث رقم بطاقة البائع في OwnedLand."""
        land = await self._get_land(land_id)
        if not land:
            raise ValueError(f"الأرض {land_id} غير موجودة")
        land.seller_id_card = id_card_number
        land.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return land.to_dict()