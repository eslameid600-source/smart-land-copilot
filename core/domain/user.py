"""
Smart Land Management Copilot — User & Account Domain Models
=============================================================
Multi-role account architecture with strict access control
for Buyer/Investor, Seller/Owner, and Certified Broker personas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict

from pydantic import BaseModel, Field, field_validator


class UserRole(str, Enum):
    BUYER_INVESTOR = "Buyer/Investor"
    SELLER_OWNER = "Seller/Owner"
    CERTIFIED_BROKER = "Certified Broker"


class BrokerVerificationStatus(str, Enum):
    PENDING_VERIFICATION = "Pending Verification"
    VERIFIED = "Verified"
    REJECTED = "Rejected"
    SUSPENDED = "Suspended"


class ListingIntent(str, Enum):
    SALE = "Sale"
    RENT = "Rent"
    PORTFOLIO_TRACKING = "Portfolio Tracking"


class DocumentType(str, Enum):
    BROKERAGE_LICENSE = "Real Estate Brokerage License"
    FINANCIAL_GUARANTEE = "Financial Guarantee"
    NATIONAL_ID = "National ID"
    COMMERCIAL_REGISTER = "Commercial Register"
    TAX_RECORD = "Tax Record"


class BrokerDocument(BaseModel):
    """A single document submitted during broker registration or verification."""
    document_id: str = Field(default="", description="Unique document identifier")
    document_type: DocumentType = Field(..., description="Type of submitted document")
    document_name: str = Field(default="", description="Original file name")
    upload_date: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp of upload",
    )
    verified: bool = Field(default=False, description="Whether the document passed admin review")
    verification_date: Optional[str] = Field(default=None)
    rejection_reason: str = Field(default="")


class UserAccount(BaseModel):
    """
    Central user account model supporting three distinct personas
    with conditional access control and role-based capabilities.
    """
    user_id: str = Field(..., description="Unique user identifier")
    full_name: str = Field(..., description="Full display name")
    email: str = Field(default="", description="Contact email address")
    phone: str = Field(default="", description="Phone number (Egyptian format)")
    role: UserRole = Field(..., description="Account role / persona")
    company_name: str = Field(default="", description="Company or fund name if applicable")
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
    )
    is_active: bool = Field(default=True)

    # ── Buyer/Investor Fields ──
    investment_budget_max_egp: Optional[float] = Field(
        default=None, ge=0, description="Maximum investment budget in EGP"
    )
    preferred_usages: List[str] = Field(
        default_factory=list, description="Preferred land usage types"
    )
    preferred_governorates: List[str] = Field(
        default_factory=list, description="Preferred governorates"
    )
    watchlist_land_ids: List[str] = Field(
        default_factory=list, description="Land IDs the investor is tracking"
    )
    portfolio_land_ids: List[str] = Field(
        default_factory=list, description="Land IDs owned in the investor portfolio"
    )

    # ── Seller/Owner Fields ──
    owned_land_ids: List[str] = Field(
        default_factory=list, description="Land IDs listed by this owner"
    )
    listing_intents: List[ListingIntent] = Field(
        default_factory=list, description="Listing intentions per owned land"
    )
    total_listed_value_egp: float = Field(default=0.0, ge=0)

    # ── Broker Fields ──
    broker_license_number: str = Field(default="")
    broker_verification_status: BrokerVerificationStatus = Field(
        default=BrokerVerificationStatus.PENDING_VERIFICATION
    )
    broker_documents: List[BrokerDocument] = Field(default_factory=list)
    broker_specializations: List[str] = Field(
        default_factory=list, description="Broker area specializations (e.g., Industrial, Residential)"
    )
    total_deals_closed: int = Field(default=0, ge=0)
    total_commission_earned_egp: float = Field(default=0.0, ge=0)
    assigned_land_ids: List[str] = Field(
        default_factory=list, description="Land IDs assigned to this broker by sellers"
    )
    performance_score: float = Field(default=0.0, ge=0.0, le=100.0)

    # ── Advertising Fields ──
    ad_credits_balance_egp: float = Field(default=0.0, ge=0)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v):
        if v and "@" not in v:
            return ""
        return v

    @property
    def is_broker_verified(self) -> bool:
        return (
            self.role == UserRole.CERTIFIED_BROKER
            and self.broker_verification_status == BrokerVerificationStatus.VERIFIED
        )

    @property
    def can_access_dashboard(self) -> bool:
        """Brokers cannot access dashboard until verified."""
        if self.role != UserRole.CERTIFIED_BROKER:
            return True
        return self.is_broker_verified

    @property
    def can_manage_listings(self) -> bool:
        """Brokers cannot manage listings until verified."""
        if self.role != UserRole.CERTIFIED_BROKER:
            return True
        return self.is_broker_verified