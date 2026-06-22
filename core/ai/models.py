"""
SQLAlchemy ORM models for the purchase module.
Tables: transactions, investor_profiles, landowner_profiles,
        loyalty_points_log, lands (minimal for purchase flow).
"""

import uuid
from decimal import Decimal
from enum import Enum as PyEnum

from purchase_module.database import Base
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# ──────────────────────────────────────────────
# Enums (PostgreSQL-native when available, str fallback)
# ──────────────────────────────────────────────

class TransactionStatus(str, PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(str, PyEnum):
    FAWRY = "fawry"
    MEEZA = "meeza"
    STRIPE = "stripe"
    WALLET = "wallet"


class LandStatus(str, PyEnum):
    AVAILABLE = "Available"
    RESERVED = "Reserved"
    SOLD = "Sold"


class WithdrawalMethod(str, PyEnum):
    BANK_TRANSFER = "bank_transfer"
    FAWRY = "fawry"
    CHECK = "check"


# ──────────────────────────────────────────────
# Land (minimal for purchase flow)
# ──────────────────────────────────────────────

class Land(Base):
    __tablename__ = "lands"

    land_id = Column(String(20), primary_key=True)
    owner_id = Column(String(36), nullable=False, index=True)
    governorate = Column(String(100), nullable=False)
    region_city = Column(String(100), nullable=False)
    total_area_sqm = Column(Integer, nullable=False)
    price_per_sqm_egp = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), nullable=False, default="Available")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Computed total (stored for performance)
    @property
    def total_price_egp(self) -> Decimal:
        return self.price_per_sqm_egp * self.total_area_sqm

    transactions = relationship("Transaction", back_populates="land")
    __table_args__ = (
        CheckConstraint(
            "price_per_sqm_egp > 0", name="ck_land_price_positive"
        ),
        CheckConstraint(
            "total_area_sqm > 0", name="ck_land_area_positive"
        ),
    )


# ──────────────────────────────────────────────
# Transaction
# ──────────────────────────────────────────────

class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    land_id = Column(
        String(20), ForeignKey("lands.land_id"), nullable=False, index=True
    )
    buyer_id = Column(String(36), nullable=False, index=True)
    seller_id = Column(String(36), nullable=False, index=True)
    amount_egp = Column(Numeric(18, 2), nullable=False)
    platform_fee_egp = Column(Numeric(18, 2), nullable=False, default=0)
    tax_amount_egp = Column(Numeric(18, 2), nullable=False, default=0)
    discount_applied_egp = Column(Numeric(18, 2), nullable=False, default=0)
    net_amount_egp = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    payment_method = Column(String(30), nullable=False, default="fawry")
    gateway_ref = Column(String(255), nullable=True)
    gateway_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    land = relationship("Land", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("amount_egp > 0", name="ck_tx_amount_positive"),
        CheckConstraint(
            "status IN ('pending','completed','failed','refunded')",
            name="ck_tx_status_valid",
        ),
        CheckConstraint(
            "payment_method IN ('fawry','meeza','stripe','wallet')",
            name="ck_tx_method_valid",
        ),
        Index("ix_tx_buyer_status", "buyer_id", "status"),
        Index("ix_tx_seller_status", "seller_id", "status"),
        Index("ix_tx_created", "created_at"),
    )


# ──────────────────────────────────────────────
# Investor Profile
# ──────────────────────────────────────────────

class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    user_id = Column(String(36), primary_key=True)
    wallet_balance_egp = Column(
        Numeric(18, 2), nullable=False, default=0
    )
    loyalty_points = Column(Integer, nullable=False, default=0)
    total_invested_egp = Column(Numeric(18, 2), nullable=False, default=0)
    total_purchases = Column(Integer, nullable=False, default=0)
    successful_purchases = Column(Integer, nullable=False, default=0)
    registration_discount_pct = Column(
        Numeric(5, 2), nullable=False, default=0
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Transactions are queried via service layer, not ORM relationship

    __table_args__ = (
        CheckConstraint(
            "wallet_balance_egp >= 0", name="ck_investor_wallet_nonneg"
        ),
        CheckConstraint(
            "loyalty_points >= 0", name="ck_investor_points_nonneg"
        ),
        CheckConstraint(
            "registration_discount_pct BETWEEN 0 AND 10",
            name="ck_investor_discount_range",
        ),
    )


# ──────────────────────────────────────────────
# Landowner Profile
# ──────────────────────────────────────────────

class LandownerProfile(Base):
    __tablename__ = "landowner_profiles"

    user_id = Column(String(36), primary_key=True)
    wallet_balance_egp = Column(
        Numeric(18, 2), nullable=False, default=0
    )
    total_earnings_egp = Column(Numeric(18, 2), nullable=False, default=0)
    total_withdrawn_egp = Column(Numeric(18, 2), nullable=False, default=0)
    lands_for_sale = Column(Integer, nullable=False, default=0)
    lands_sold = Column(Integer, nullable=False, default=0)
    withdrawal_method = Column(String(30), nullable=True)
    bank_account_ref = Column(String(100), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Transactions are queried via service layer, not ORM relationship

    __table_args__ = (
        CheckConstraint(
            "wallet_balance_egp >= 0", name="ck_landowner_wallet_nonneg"
        ),
    )


# ──────────────────────────────────────────────
# Loyalty Points Log
# ──────────────────────────────────────────────

class LoyaltyPointsLog(Base):
    __tablename__ = "loyalty_points_log"

    log_id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id = Column(
        String(36), nullable=False, index=True
    )
    transaction_id = Column(
        String(36), nullable=True
    )
    points_earned = Column(Integer, nullable=False, default=0)
    points_used = Column(Integer, nullable=False, default=0)
    balance_after = Column(Integer, nullable=False, default=0)
    reason = Column(String(200), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_loyalty_user_created", "user_id", "created_at"),
    )