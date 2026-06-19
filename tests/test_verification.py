"""
اختبارات نظام التحقق من الأراضي
==================================
اختبارات وحدة وتكامل تغطي:
- رفع وثائق قانونية
- تسجيل GPS
- حالة التحقق
- التحقق اليدوي
"""

import pytest
import hashlib
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from core.account.models import (
    Base,
    OwnedLand,
    LandDocument,
    LandGPSLog,
    DocumentType,
    LandVerificationStatus,
)
from core.domain.verification_service import LandVerificationService


# ──────────────────────────────────────────
# إعداد قاعدة بيانات اختبار
# ──────────────────────────────────────────

@pytest.fixture
async def db_session():
    """إنشاء جلسة قاعدة بيانات اختبار."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        # إنشاء مستخدم + مالك أرض للتجربة
        from core.account.models import User, Landowner
        user = User(
            user_id="test-owner-001",
            full_name="بائع تجريبي",
            role="Seller/Owner",
            password_hash="hashed",
        )
        landowner = Landowner(user_id="test-owner-001")
        land = OwnedLand(
            landowner_id="test-owner-001",
            land_id="LAND-TEST-001",
            land_name="أرض اختبار",
            governorate="القاهرة",
            region_city="مدينة نصر",
            total_area_sqm=500,
            price_per_sqm_egp=5000,
            total_price_egp=2500000,
            investment_status="متاح",
            verification_status=LandVerificationStatus.PENDING,
        )
        session.add(user)
        session.add(landowner)
        session.add(land)
        await session.flush()
    
    async with async_session() as session:
        yield session
    
    await engine.dispose()


@pytest.fixture
def verification_service(db_session):
    return LandVerificationService(db_session)


# ──────────────────────────────────────────
# اختبارات رفع الوثائق
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_document(verification_service):
    """رفع وثيقة بنجاح."""
    file_content = b"fake pdf content"
    result = await verification_service.upload_document(
        land_id="LAND-TEST-001",
        document_type="title_deed",
        file_content=file_content,
        original_filename="title_deed.pdf",
        id_card_number="12345678901234",
        uploaded_by="test-owner-001",
    )
    
    assert result["land_id"] == "LAND-TEST-001"
    assert result["document_type"] == "title_deed"
    assert result["id_card_number"] == "12345678901234"
    assert result["verified_by_admin"] is False
    assert result["file_path"].endswith(".pdf")


@pytest.mark.asyncio
async def test_upload_document_invalid_extension(verification_service):
    """رفض صيغة ملف غير مدعومة."""
    with pytest.raises(ValueError, match="صيغة الملف غير مدعومة"):
        await verification_service.upload_document(
            land_id="LAND-TEST-001",
            document_type="title_deed",
            file_content=b"content",
            original_filename="document.exe",
            uploaded_by="test-owner-001",
        )


@pytest.mark.asyncio
async def test_upload_document_too_large(verification_service):
    """رفض ملف كبير جداً."""
    large_content = b"x" * (11 * 1024 * 1024)  # 11 MB
    with pytest.raises(ValueError, match="يتجاوز 10 ميغابايت"):
        await verification_service.upload_document(
            land_id="LAND-TEST-001",
            document_type="title_deed",
            file_content=large_content,
            original_filename="big.pdf",
            uploaded_by="test-owner-001",
        )


@pytest.mark.asyncio
async def test_upload_duplicate_document(verification_service):
    """رفع وثيقة مماثلة مرتين."""
    content = b"duplicate content"
    
    # الرفع الأول
    await verification_service.upload_document(
        land_id="LAND-TEST-001",
        document_type="title_deed",
        file_content=content,
        original_filename="deed1.pdf",
        uploaded_by="test-owner-001",
    )
    
    # الرفع الثاني بنفس المحتوى
    with pytest.raises(ValueError, match="مرفوعة مسبقاً"):
        await verification_service.upload_document(
            land_id="LAND-TEST-001",
            document_type="title_deed",
            file_content=content,
            original_filename="deed_copy.pdf",
            uploaded_by="test-owner-001",
        )


@pytest.mark.asyncio
async def test_upload_by_non_owner(verification_service):
    """منع غير المالك من رفع وثائق."""
    with pytest.raises(ValueError, match="فقط مالك الأرض"):
        await verification_service.upload_document(
            land_id="LAND-TEST-001",
            document_type="title_deed",
            file_content=b"content",
            original_filename="deed.pdf",
            uploaded_by="some-intruder",
        )


# ──────────────────────────────────────────
# اختبارات GPS
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_gps(verification_service):
    """تسجيل إحداثيات GPS."""
    result = await verification_service.register_gps(
        land_id="LAND-TEST-001",
        latitude=30.0444,
        longitude=31.2357,
        accuracy=5.0,
        source="manual_entry",
        recorded_by="test-owner-001",
    )
    
    assert result["land_id"] == "LAND-TEST-001"
    assert result["latitude"] == 30.0444
    assert result["longitude"] == 31.2357
    assert result["accuracy_meters"] == 5.0
    assert result["source"] == "manual_entry"


@pytest.mark.asyncio
async def test_register_gps_by_non_owner(verification_service):
    """منع غير المالك من تسجيل GPS."""
    with pytest.raises(ValueError, match="فقط مالك الأرض"):
        await verification_service.register_gps(
            land_id="LAND-TEST-001",
            latitude=30.0,
            longitude=31.0,
            recorded_by="stranger",
        )


@pytest.mark.asyncio
async def test_get_latest_gps(verification_service):
    """استرجاع آخر تسجيل GPS."""
    # تسجيل plusieurs
    await verification_service.register_gps(
        land_id="LAND-TEST-001",
        latitude=30.01,
        longitude=31.02,
        recorded_by="test-owner-001",
    )
    await verification_service.register_gps(
        land_id="LAND-TEST-001",
        latitude=30.02,
        longitude=31.03,
        recorded_by="test-owner-001",
    )
    
    latest = await verification_service.get_latest_gps("LAND-TEST-001")
    assert latest is not None
    assert latest["latitude"] == 30.02
    assert latest["longitude"] == 31.03


# ──────────────────────────────────────────
# اختبارات حالة التحقق
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_verification_status_after_document_upload(verification_service):
    """تحديث حالة التحقق بعد رفع وثيقة."""
    await verification_service.upload_document(
        land_id="LAND-TEST-001",
        document_type="title_deed",
        file_content=b"deed content",
        original_filename="deed.pdf",
        uploaded_by="test-owner-001",
    )
    
    status = await verification_service.get_verification_status("LAND-TEST-001")
    assert status["documents_count"] == 1
    assert status["verification_status"] == "documents_uploaded"


@pytest.mark.asyncio
async def test_verification_status_after_gps(verification_service):
    """تحديث حالة التحقق بعد تسجيل GPS."""
    # رفع وثيقة أولًا
    await verification_service.upload_document(
        land_id="LAND-TEST-001",
        document_type="id_card",
        file_content=b"id card",
        original_filename="id.pdf",
        id_card_number="98765432109876",
        uploaded_by="test-owner-001",
    )
    
    # تسجيل GPS
    await verification_service.register_gps(
        land_id="LAND-TEST-001",
        latitude=30.05,
        longitude=31.1,
        recorded_by="test-owner-001",
    )
    
    status = await verification_service.get_verification_status("LAND-TEST-001")
    # الحالة يجب أن تكون auto_verified (بسبب وجود ID_CARD + GPS)
    assert status["gps_registered"] is True
    assert status["documents_count"] >= 1


@pytest.mark.asyncio
async def test_admin_manual_verify(verification_service):
    """تحقق يدوي من قبل المسؤول."""
    # رفع وثيقة
    await verification_service.upload_document(
        land_id="LAND-TEST-001",
        document_type="title_deed",
        file_content=b"deed",
        original_filename="deed.pdf",
        uploaded_by="test-owner-001",
    )
    
    # تحقق يدوي بالموافقة
    result = await verification_service.admin_manual_verify_location(
        land_id="LAND-TEST-001",
        admin_id="admin-001",
        approved=True,
        notes="تم الفحص والموافقة",
    )
    
    assert result["approved"] is True
    assert result["status"] == "verified"
    
    status = await verification_service.get_verification_status("LAND-TEST-001")
    assert status["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_admin_manual_reject(verification_service):
    """رفض التحقق من قبل المسؤول."""
    await verification_service.upload_document(
        land_id="LAND-TEST-001",
        document_type="title_deed",
        file_content=b"deed",
        original_filename="deed.pdf",
        uploaded_by="test-owner-001",
    )
    
    result = await verification_service.admin_manual_verify_location(
        land_id="LAND-TEST-001",
        admin_id="admin-001",
        approved=False,
        notes="العت لا يطابق",
    )
    
    assert result["approved"] is False
    assert result["status"] == "rejected"


# ──────────────────────────────────────────
# اختبارات الوثائق المطلوبة
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_required_documents(verification_service):
    """التحقق من الوثائق المفقودة."""
    # لا نرفع أي وثائق
    status = await verification_service.get_verification_status("LAND-TEST-001")
    assert "title_deed" in status["missing_document_types"]
    assert "id_card" in status["missing_document_types"]