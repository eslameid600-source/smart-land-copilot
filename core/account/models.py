"""
Smart Land Copilot — نماذج قاعدة البيانات (SQLAlchemy ORM)
==========================================================
الجداول المركزية للتطبيق:

- investors            – حسابات المستثمرين
- landowners           – حسابات ملاك الأراضي
- owned_lands          – الأراضي المُعلنة من قبل الملاك
- brokers              – بيانات الوسطاء
- broker_assignments   – تعيين وسيط لأرض
- broker_transactions  – سجل عمولات الوسطاء
- land_documents       – وثائق قانونية للأراضي
- land_gps_logs        – سجلات إحداثيات GPS
- users                – جدول المستخدمين المركزي (دور، بريد، إلخ)

تم تصميم النماذج لتدعم:
    - مستثمر (Investor)
    - مالك أرض (Landowner)
    - وسيط (Broker)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Numeric,
    Integer,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    Text,
    Boolean,
    JSON,
    Enum,
    Float,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


# ──────────────────────────────────────────────
# Base Declaration
# ──────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class UserRole(str, PyEnum):
    """أدوار المستخدمين في المنصة."""
    BUYER_INVESTOR = "Buyer/Investor"
    SELLER_OWNER = "Seller/Owner"
    CERTIFIED_BROKER = "Certified Broker"
    ADMIN = "Admin"


class UserStatus(str, PyEnum):
    """حالة حساب المستخدم."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class BrokerStatus(str, PyEnum):
    """حالة الوسيط."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class BrokerAssignmentStatus(str, PyEnum):
    """حالة تعيين الوسيط."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BrokerTransactionStatus(str, PyEnum):
    """حالة عملية عمولة الوسيط."""
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class DocumentType(str, PyEnum):
    """أنواع الوثائق القانونية."""
    TITLE_DEED = "title_deed"           # صورة من سند الملكية
    CONTRACT = "contract"               # عقد بيع أو إيجار
    TAX_RECEIPT = "tax_receipt"         # إيصال ضريبي
    ID_CARD = "id_card"                 # بطاقة شخصية / سجل تجاري
    COMMERCIAL_REGISTER = "commercial_register"  # السجل التجاري
    OTHER = "other"                     # وثيقة أخرى


class GPSSource(str, PyEnum):
    """مصدر إحداثيات GPS."""
    BROWSER_GEOLOCATION = "browser_geolocation"   # من متصفح المستخدم
    MOBILE_APP = "mobile_app"                     # من تطبيق موبايل
    MANUAL_ENTRY = "manual_entry"                 # إدخال يدوي
    ADMIN_VERIFIED = "admin_verified"             # تم التحقق بواسطة المسؤول


class LandVerificationStatus(str, PyEnum):
    """حالة التحقق من صحة الأرض."""
    PENDING = "pending"                 # في انتظار الوثائق
    DOCUMENTS_UPLOADED = "documents_uploaded"   # تم رفع الوثائق
    GPS_REGISTERED = "gps_registered"    # تم تسجيل الموقع
    AUTO_VERIFIED = "auto_verified"       # تطابق تلقائي مع الوثائق
    MANUAL_REVIEW = "manual_review"       # يحتاج مراجعة يدوية
    VERIFIED = "verified"                 # تم التحقق الكامل
    REJECTED = "rejected"                 # مرفوض


# ──────────────────────────────────────────────
# Users (جدول المستخدمين المركزي)
# ──────────────────────────────────────────────

class User(Base):
    """
    جدول المستخدمين المركزي.
    يُستخدم للمصادقة والصلاحيات العامة.
    كل من المستثمر ومالك الأرض والوسيط له سجل هنا.
    """
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(36), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=True)
    phone_number = Column(String(20), nullable=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.SELLER_OWNER)
    status = Column(Enum(UserStatus), nullable=False, default=UserStatus.PENDING_VERIFICATION)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # العلاقات
    investor_profile = relationship("Investor", back_populates="user", uselist=False, cascade="all, delete-orphan")
    landowner_profile = relationship("Landowner", back_populates="user", uselist=False, cascade="all, delete-orphan")
    broker_profile = relationship("Broker", back_populates="user", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_user_role", "role"),
        Index("ix_user_status", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "full_name": self.full_name,
            "email": self.email,
            "phone_number": self.phone_number,
            "role": self.role.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────
# Investors (المستثمرون)
# ──────────────────────────────────────────────

class Investor(Base):
    """
    ملف المستثمر — بيانات المحفظة والولاءات.
    مرتبط بجدول users عبر user_id.
    """
    __tablename__ = "investors"

    user_id = Column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    wallet_balance_egp = Column(Numeric(18, 2), nullable=False, default=0)
    frozen_balance_egp = Column(Numeric(18, 2), nullable=False, default=0)
    loyalty_points = Column(Integer, nullable=False, default=0)
    total_lands_purchased = Column(Integer, nullable=False, default=0)
    total_spent_egp = Column(Numeric(18, 2), nullable=False, default=0)
    investment_budget_max_egp = Column(Numeric(18, 2), nullable=True)
    preferred_governorates = Column(JSON, nullable=True, default=list)
    preferred_usages = Column(JSON, nullable=True, default=list)
    watchlist_land_ids = Column(JSON, nullable=True, default=list)
    portfolio_land_ids = Column(JSON, nullable=True, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # العلاقة
    user = relationship("User", back_populates="investor_profile")
    wallet_transactions = relationship("WalletTransaction", back_populates="investor", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("wallet_balance_egp >= 0", name="ck_investor_wallet_nonneg"),
        CheckConstraint("frozen_balance_egp >= 0", name="ck_investor_frozen_nonneg"),
        CheckConstraint("loyalty_points >= 0", name="ck_investor_points_nonneg"),
    )

    @property
    def available_balance_egp(self) -> Decimal:
        return self.wallet_balance_egp - self.frozen_balance_egp

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "wallet_balance_egp": float(self.wallet_balance_egp),
            "frozen_balance_egp": float(self.frozen_balance_egp),
            "available_balance_egp": float(self.available_balance_egp),
            "loyalty_points": self.loyalty_points,
            "total_lands_purchased": self.total_lands_purchased,
            "total_spent_egp": float(self.total_spent_egp),
            "investment_budget_max_egp": float(self.investment_budget_max_egp) if self.investment_budget_max_egp else None,
            "preferred_governorates": self.preferred_governorates,
            "preferred_usages": self.preferred_usages,
            "watchlist_land_ids": self.watchlist_land_ids,
            "portfolio_land_ids": self.portfolio_land_ids,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────
# Landowners (ملّاك الأراضي)
# ──────────────────────────────────────────────

class Landowner(Base):
    """
    ملف مالك الأرض.
    يحتوي على إحصائيات البيع والعمولات الإجمالية.
    """
    __tablename__ = "landowners"

    user_id = Column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    default_commission_pct = Column(Numeric(5, 2), nullable=False, default=2.5)
    total_lands_listed = Column(Integer, nullable=False, default=0)
    active_lands_count = Column(Integer, nullable=False, default=0)
    total_sales_egp = Column(Numeric(18, 2), nullable=False, default=0)
    total_commission_earned_egp = Column(Numeric(18, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # العلاقة
    user = relationship("User", back_populates="landowner_profile")
    lands = relationship("OwnedLand", back_populates="landowner", cascade="all, delete-orphan")
    transactions = relationship("LandownerTransaction", back_populates="landowner", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("default_commission_pct BETWEEN 0 AND 50", name="ck_landowner_commission_range"),
        CheckConstraint("total_lands_listed >= 0", name="ck_landowner_listed_nonneg"),
        CheckConstraint("active_lands_count >= 0", name="ck_landowner_active_nonneg"),
    )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "default_commission_pct": float(self.default_commission_pct),
            "total_lands_listed": self.total_lands_listed,
            "active_lands_count": self.active_lands_count,
            "total_sales_egp": float(self.total_sales_egp),
            "total_commission_earned_egp": float(self.total_commission_earned_egp),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ──────────────────────────────────────────────
# Owned Lands (الأراضي المُعلنة)
# ──────────────────────────────────────────────

class OwnedLand(Base):
    """
    سجل الأراضي المُعلنة من قبل مالك.
    كل سجل مرتبط بمالك واحد ويمكن أن يُعيّن له وسيط واحد.
    """
    __tablename__ = "owned_lands"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    landowner_id = Column(String(36), ForeignKey("landowners.user_id", ondelete="CASCADE"), nullable=False, index=True)
    land_id = Column(String(50), unique=True, nullable=False, index=True)
    land_name = Column(String(200), nullable=False)
    governorate = Column(String(100), nullable=False)
    region_city = Column(String(100), nullable=False)
    total_area_sqm = Column(Integer, nullable=False)
    price_per_sqm_egp = Column(Numeric(18, 2), nullable=False)
    total_price_egp = Column(Numeric(18, 2), nullable=False)
    investment_status = Column(String(50), nullable=False, default="متاح")
    listing_intent = Column(String(50), nullable=False, default="Sale")
    description_ar = Column(Text, nullable=True)
    images = Column(JSON, nullable=True, default=list)
    broker_id = Column(String(36), nullable=True, index=True)
    commission_percent = Column(Numeric(5, 2), nullable=True)
    verification_status = Column(Enum(LandVerificationStatus), nullable=False, default=LandVerificationStatus.PENDING)
    seller_id_card = Column(String(50), nullable=True)
    listed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    views_count = Column(Integer, nullable=False, default=0)
    inquiries_count = Column(Integer, nullable=False, default=0)
    sold_at = Column(DateTime(timezone=True), nullable=True)
    buyer_id = Column(String(36), nullable=True)

    # العلاقات
    landowner = relationship("Landowner", back_populates="lands")
    documents = relationship("LandDocument", back_populates="land", cascade="all, delete-orphan")
    gps_logs = relationship("LandGPSLog", back_populates="land", cascade="all, delete-orphan")
    broker_assignments = relationship("BrokerAssignment", back_populates="land", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("price_per_sqm_egp > 0", name="ck_land_price_positive"),
        CheckConstraint("total_area_sqm > 0", name="ck_land_area_positive"),
        CheckConstraint("total_price_egp > 0", name="ck_land_total_price_positive"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "landowner_id": self.landowner_id,
            "land_id": self.land_id,
            "land_name": self.land_name,
            "governorate": self.governorate,
            "region_city": self.region_city,
            "total_area_sqm": self.total_area_sqm,
            "price_per_sqm_egp": float(self.price_per_sqm_egp),
            "total_price_egp": float(self.total_price_egp),
            "investment_status": self.investment_status,
            "listing_intent": self.listing_intent,
            "description_ar": self.description_ar,
            "images": self.images or [],
            "broker_id": self.broker_id,
            "commission_percent": float(self.commission_percent) if self.commission_percent else None,
            "verification_status": self.verification_status.value if self.verification_status else "pending",
            "seller_id_card": self.seller_id_card,
            "listed_at": self.listed_at.isoformat() if self.listed_at else None,
            "views_count": self.views_count,
            "inquiries_count": self.inquiries_count,
            "sold_at": self.sold_at.isoformat() if self.sold_at else None,
            "buyer_id": self.buyer_id,
        }


# ──────────────────────────────────────────────
# Brokers (الوسطاء)
# ──────────────────────────────────────────────

class Broker(Base):
    """
    جدول الوسطاء.
    كل وسيط مرتبط بمستخدم من المستخدمين (role = CERTIFIED_BROKER).
    """
    __tablename__ = "brokers"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(36), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    phone_number = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)
    company_name = Column(String(200), nullable=True)
    license_number = Column(String(100), nullable=True)
    default_commission_rate = Column(Numeric(5, 2), nullable=False, default=2.5)
    broker_code = Column(String(50), unique=True, nullable=False, index=True)
    bio = Column(Text, nullable=True)
    specialization = Column(JSON, nullable=True, default=list)
    total_deals_closed = Column(Integer, nullable=False, default=0)
    total_commission_earned_egp = Column(Numeric(18, 2), nullable=False, default=0)
    rating_avg = Column(Numeric(3, 2), nullable=True)
    rating_count = Column(Integer, nullable=False, default=0)
    status = Column(Enum(BrokerStatus), nullable=False, default=BrokerStatus.INACTIVE)
    verified_by_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # العلاقات (نظام التقييم سيُضاف لاحقاً مثل Comment)
    assignments = relationship("BrokerAssignment", back_populates="broker", cascade="all, delete-orphan")
    transactions = relationship("BrokerTransaction", back_populates="broker", cascade="all, delete-orphan")
    user = relationship("User", backref="broker_profile_ref")

    __table_args__ = (
        CheckConstraint("default_commission_rate BETWEEN 1 AND 20", name="ck_broker_commission_range"),
        CheckConstraint("default_commission_rate >= 0", name="ck_broker_commission_nonneg"),
        CheckConstraint("total_deals_closed >= 0", name="ck_broker_deals_nonneg"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "full_name": self.full_name,
            "phone_number": self.phone_number,
            "email": self.email,
            "company_name": self.company_name,
            "license_number": self.license_number,
            "default_commission_rate": float(self.default_commission_rate),
            "broker_code": self.broker_code,
            "bio": self.bio,
            "specialization": self.specialization or [],
            "total_deals_closed": self.total_deals_closed,
            "total_commission_earned_egp": float(self.total_commission_earned_egp),
            "rating_avg": float(self.rating_avg) if self.rating_avg else None,
            "rating_count": self.rating_count,
            "status": self.status.value if self.status else "inactive",
            "verified_by_admin": self.verified_by_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────
# Broker Assignments (تعيين وسيط لأرض)
# ──────────────────────────────────────────────

class BrokerAssignment(Base):
    """
    جدول تعيين الوسيط لأرض معينة.
    يمكن أن يكون هناك وسيط واحد لكل أرض في نفس الوقت.
    """
    __tablename__ = "broker_assignments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_id = Column(String(50), ForeignKey("owned_lands.land_id", ondelete="CASCADE"), nullable=False, index=True)
    broker_id = Column(PG_UUID(as_uuid=True), ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False, index=True)
    commission_percent = Column(Numeric(5, 2), nullable=True)  # قد تختلف عن النسبة الافتراضية
    status = Column(Enum(BrokerAssignmentStatus), nullable=False, default=BrokerAssignmentStatus.PENDING)
    notes = Column(Text, nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    activated_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # العلاقات
    land = relationship("OwnedLand", back_populates="broker_assignments")
    broker = relationship("Broker", back_populates="assignments")

    __table_args__ = (
        Index("ix_broker_assignment_land", "land_id"),
        Index("ix_broker_assignment_broker", "broker_id"),
        # farming constraint: land_id + status combination uniqueness for active
        # MySQL/PostgreSQL both support partial indexes, but SQLite doesn't.
        # We'll enforce uniqueness at application level for now.
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "land_id": self.land_id,
            "broker_id": str(self.broker_id),
            "commission_percent": float(self.commission_percent) if self.commission_percent else None,
            "status": self.status.value if self.status else "pending",
            "notes": self.notes,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
        }


# ──────────────────────────────────────────────
# Broker Transactions (عمولات الوسطاء)
# ──────────────────────────────────────────────

class BrokerTransaction(Base):
    """
    سجل عمولات الوسيط — كل عملية دفع أو مستحقة.
    مرتبط بجدول owned_lands (البيع) أو by transaction_id مباشرة.
    """
    __tablename__ = "broker_transactions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_id = Column(PG_UUID(as_uuid=True), ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id = Column(String(100), nullable=True, index=True)
    land_id = Column(String(50), nullable=True, index=True)
    sale_amount_egp = Column(Numeric(18, 2), nullable=False)
    commission_rate_pct = Column(Numeric(5, 2), nullable=False)
    commission_amount_egp = Column(Numeric(18, 2), nullable=False)
    platform_fee_egp = Column(Numeric(18, 2), nullable=False, default=0)
    net_commission_egp = Column(Numeric(18, 2), nullable=False)
    status = Column(Enum(BrokerTransactionStatus), nullable=False, default=BrokerTransactionStatus.PENDING)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # العلاقة
    broker = relationship("Broker", back_populates="transactions")

    __table_args__ = (
        Index("ix_broker_tx_broker", "broker_id"),
        Index("ix_broker_tx_status", "status"),
        CheckConstraint("sale_amount_egp > 0", name="ck_broker_tx_sale_positive"),
        CheckConstraint("commission_rate_pct >= 0", name="ck_broker_tx_rate_nonneg"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "broker_id": str(self.broker_id),
            "transaction_id": self.transaction_id,
            "land_id": self.land_id,
            "sale_amount_egp": float(self.sale_amount_egp),
            "commission_rate_pct": float(self.commission_rate_pct),
            "commission_amount_egp": float(self.commission_amount_egp),
            "platform_fee_egp": float(self.platform_fee_egp),
            "net_commission_egp": float(self.net_commission_egp),
            "status": self.status.value if self.status else "pending",
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────
# Land Documents (وثائق الأراضي)
# ──────────────────────────────────────────────

class LandDocument(Base):
    """
    وثائق قانونية لكل أرض.
    يجب أن يرفع البائع الوثائق المطلوبة قبل تأكيد ملكية الأرض.
    """
    __tablename__ = "land_documents"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_id = Column(String(50), ForeignKey("owned_lands.land_id", ondelete="CASCADE"), nullable=False, index=True)
    document_type = Column(Enum(DocumentType), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=True)  # SHA-256 hash for deduplication
    file_size_kb = Column(Integer, nullable=True)
    original_filename = Column(String(255), nullable=True)
    id_card_number = Column(String(50), nullable=True)  # رقم البطاقة أو السجل التجاري
    uploaded_by = Column(String(36), nullable=False)  # user_id
    verified_by_admin = Column(Boolean, nullable=False, default=False)
    verified_by_admin_id = Column(String(36), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    admin_notes = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # العلاقة
    land = relationship("OwnedLand", back_populates="documents")

    __table_args__ = (
        Index("ix_land_doc_land", "land_id"),
        Index("ix_land_doc_type", "document_type"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "land_id": self.land_id,
            "document_type": self.document_type.value if self.document_type else "other",
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "file_size_kb": self.file_size_kb,
            "original_filename": self.original_filename,
            "id_card_number": self.id_card_number,
            "uploaded_by": self.uploaded_by,
            "verified_by_admin": self.verified_by_admin,
            "verified_by_admin_id": self.verified_by_admin_id,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "admin_notes": self.admin_notes,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


# ──────────────────────────────────────────────
# Land GPS Logs (سجلات المواقع)
# ──────────────────────────────────────────────

class LandGPSLog(Base):
    """
    سجل إحداثيات GPS لكل أرض.
    يمكن تسجيل عدة مواقع من قبل البائع والمسؤول.
    """
    __tablename__ = "land_gps_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_id = Column(String(50), ForeignKey("owned_lands.land_id", ondelete="CASCADE"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy_meters = Column(Float, nullable=True)  # دقة الإحداثيات بالمتر
    altitude_meters = Column(Float, nullable=True)
    source = Column(Enum(GPSSource), nullable=False, default=GPSSource.MANUAL_ENTRY)
    recorded_by = Column(String(36), nullable=False)  # user_id
    is_verified = Column(Boolean, nullable=False, default=False)
    verification_note = Column(Text, nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # العلاقة
    land = relationship("OwnedLand", back_populates="gps_logs")

    __table_args__ = (
        Index("ix_land_gps_land", "land_id"),
        Index("ix_land_gps_recorded", "recorded_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "land_id": self.land_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy_meters": self.accuracy_meters,
            "altitude_meters": self.altitude_meters,
            "source": self.source.value if self.source else "manual_entry",
            "recorded_by": self.recorded_by,
            "is_verified": self.is_verified,
            "verification_note": self.verification_note,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


# ──────────────────────────────────────────────
# Wallet Transactions (معاملات المحفظة)
# ──────────────────────────────────────────────

class WalletTransaction(Base):
    """
    سجل جميع معاملات المحفظة للمستثمرين.
    """
    __tablename__ = "wallet_transactions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investor_id = Column(String(36), ForeignKey("investors.user_id", ondelete="CASCADE"), nullable=False, index=True)
    tx_type = Column(String(50), nullable=False)  # deposit, purchase, withdrawal, refund, commission
    amount_egp = Column(Numeric(18, 2), nullable=False)
    balance_after = Column(Numeric(18, 2), nullable=False)
    reference_id = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # العلاقة
    investor = relationship("Investor", back_populates="wallet_transactions")

    __table_args__ = (
        Index("ix_wallet_tx_investor", "investor_id"),
        Index("ix_wallet_tx_created", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "investor_id": self.investor_id,
            "tx_type": self.tx_type,
            "amount_egp": float(self.amount_egp),
            "balance_after": float(self.balance_after),
            "reference_id": self.reference_id,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────
# Landowner Transactions (معاملات ملاك الأراضي)
# ──────────────────────────────────────────────

class LandownerTransaction(Base):
    """
    سجل معاملات ملاك الأراضي (عمولات، إيرادات بيع).
    """
    __tablename__ = "landowner_transactions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    landowner_id = Column(String(36), ForeignKey("landowners.user_id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type = Column(String(50), nullable=False)  # commission_earned, sale_income, withdrawal
    amount_egp = Column(Numeric(18, 2), nullable=False)
    land_id = Column(String(50), nullable=True)
    reference_id = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # العلاقة
    landowner = relationship("Landowner", back_populates="transactions")

    __table_args__ = (
        Index("ix_landowner_tx_landowner", "landowner_id"),
        Index("ix_landowner_tx_type", "transaction_type"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "landowner_id": self.landowner_id,
            "transaction_type": self.transaction_type,
            "amount_egp": float(self.amount_egp),
            "land_id": self.land_id,
            "reference_id": self.reference_id,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────
# Exports
# ──────────────────────────────────────────────

__all__ = [
    "Base",
    "UserRole",
    "UserStatus",
    "BrokerStatus",
    "BrokerAssignmentStatus",
    "BrokerTransactionStatus",
    "DocumentType",
    "GPSSource",
    "LandVerificationStatus",
    "User",
    "Investor",
    "Landowner",
    "OwnedLand",
    "Broker",
    "BrokerAssignment",
    "BrokerTransaction",
    "LandDocument",
    "LandGPSLog",
    "WalletTransaction",
    "LandownerTransaction",
]