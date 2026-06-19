"""
Smart Land Management Copilot — Auction & Marketplace Models
=============================================================
Pydantic models for the Digital Land Auction & Trading Marketplace
including bidding engine, commission/fee structures, and land sourcing.
"""

from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, field_validator


class AuctionStatus(str, Enum):
    PENDING = "Pending"
    LIVE = "Live"
    ENDED = "Ended"
    CANCELLED = "Cancelled"


class BidStatus(str, Enum):
    PENDING = "Pending"
    WINNING = "Winning"
    OUTBID = "Outbid"
    WON = "Won"
    LOST = "Lost"


class LeadStatus(str, Enum):
    SUBMITTED = "Submitted"
    DOCUMENTS_UPLOADED = "Documents Uploaded"
    NOTARY_VERIFIED = "Verified by Notary"
    REJECTED = "Rejected"


class ListingSource(str, Enum):
    OWNER_DIRECT = "Owner Direct"
    SCOUT_SOURCED = "Scout Sourced"


class Bid(BaseModel):
    """Single bid record within an auction."""
    bid_id: str = Field(..., description="Unique bid identifier")
    auction_id: str = Field(..., description="Parent auction identifier")
    bidder_id: str = Field(..., description="Registered bidder identifier")
    bidder_name: str = Field(default="", description="Bidder display name")
    bid_amount_egp: float = Field(..., gt=0, description="Bid amount in EGP")
    bid_per_sqm_egp: float = Field(default=0.0, ge=0, description="Bid amount per square meter")
    bid_timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp of when the bid was placed",
    )
    status: BidStatus = Field(default=BidStatus.PENDING, description="Current bid status")
    is_auto_bid: bool = Field(default=False, description="Whether this is an automated proxy bid")


class AuctionRecord(BaseModel):
    """
    Full auction record for a land parcel listed for public bidding.
    Extends the existing Investment_Status='Public Auction' with a
    complete bidding engine state machine.
    """
    auction_id: str = Field(..., description="Unique auction identifier")
    land_id: str = Field(..., description="Reference to the land parcel")
    governorate: str = Field(default="")
    region_city: str = Field(default="")
    total_area_sqm: int = Field(default=0, gt=0)
    allowed_usage: str = Field(default="")

    base_price_egp: float = Field(..., gt=0, description="Minimum starting price in EGP")
    base_price_per_sqm_egp: float = Field(default=0.0, gt=0)
    current_highest_bid_egp: float = Field(default=0.0, ge=0)
    current_highest_bid_per_sqm_egp: float = Field(default=0.0, ge=0)
    bid_count: int = Field(default=0, ge=0)
    registered_bidders_count: int = Field(default=0, ge=0)

    auction_start_date: Optional[str] = Field(default=None, description="Auction open date (ISO)")
    auction_end_date: Optional[str] = Field(default=None, description="Auction close date (ISO)")
    status: AuctionStatus = Field(default=AuctionStatus.PENDING)

    minimum_increment_pct: float = Field(
        default=2.0, ge=0.1, le=20.0,
        description="Minimum percentage above current highest bid for a valid new bid",
    )
    reserve_price_egp: Optional[float] = Field(
        default=None, ge=0,
        description="Hidden reserve price; if not met, seller may reject the sale",
    )

    winning_bid: Optional[Bid] = Field(default=None, description="The winning bid after auction ends")
    all_bids: List[Bid] = Field(default_factory=list, description="Chronological bid history")

    listing_source: ListingSource = Field(
        default=ListingSource.OWNER_DIRECT,
        description="Whether the listing was sourced by the owner or a scout",
    )
    scout_id: Optional[str] = Field(default=None, description="Scout user ID if scout-sourced")
    scout_name: Optional[str] = Field(default=None, description="Scout display name")

    def compute_minimum_next_bid(self) -> float:
        """Calculate the minimum acceptable next bid amount."""
        if self.current_highest_bid_egp <= 0:
            return round(self.base_price_egp * (1 + self.minimum_increment_pct / 100), 2)
        increment = self.current_highest_bid_egp * (self.minimum_increment_pct / 100)
        return round(self.current_highest_bid_egp + increment, 2)

    def is_auction_live(self) -> bool:
        """Check if the auction is currently accepting bids."""
        if self.status != AuctionStatus.LIVE:
            return False
        if self.auction_end_date:
            try:
                end_dt = datetime.fromisoformat(self.auction_end_date)
                return datetime.now() < end_dt
            except (ValueError, TypeError):
                return True
        return True

    def time_remaining(self) -> Optional[str]:
        """Return human-readable time remaining or None if ended."""
        if not self.auction_end_date:
            return None
        try:
            end_dt = datetime.fromisoformat(self.auction_end_date)
            delta = end_dt - datetime.now()
            if delta.total_seconds() <= 0:
                return "Ended"
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes = remainder // 60
            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        except (ValueError, TypeError):
            return None


class TransactionFeeBreakdown(BaseModel):
    """
    Multi-tiered commission and fee breakdown for a land transaction.

    Calculates and exposes every party's exact financial cut from the
    total transaction value, including Egyptian government duties.
    """
    land_id: str = Field(default="")
    auction_id: Optional[str] = Field(default=None)
    total_transaction_value_egp: float = Field(..., gt=0, description="Final sale price / highest bid")
    total_area_sqm: int = Field(default=1)
    transaction_type: str = Field(default="Direct Sale", description="Direct Sale or Auction")

    # ── Platform Commission ──
    platform_commission_pct: float = Field(
        default=2.5, ge=0, le=15,
        description="Marketplace platform commission percentage",
    )
    platform_commission_egp: float = Field(default=0.0, ge=0)

    # ── Sourcing Agent / Scout Fee ──
    scout_fee_pct: float = Field(
        default=1.5, ge=0, le=10,
        description="Scout/sourcing agent fee percentage",
    )
    scout_fee_egp: float = Field(default=0.0, ge=0)
    scout_name: str = Field(default="")
    scout_eligible: bool = Field(default=False, description="Whether a scout fee applies")

    # ── Egyptian Government Duties ──
    real_estate_disposal_tax_pct: float = Field(
        default=2.5, ge=0, le=10,
        description="Egyptian Real Estate Disposal Tax (2.5%)",
    )
    real_estate_disposal_tax_egp: float = Field(default=0.0, ge=0)

    registration_notary_fee_pct: float = Field(
        default=3.0, ge=0, le=10,
        description="Estimated Shahr Eqary (Land Registration) + Notary fees",
    )
    registration_notary_fee_egp: float = Field(default=0.0, ge=0)

    stamp_duty_pct: float = Field(
        default=0.5, ge=0, le=5,
        description="Egyptian stamp duty on transactions",
    )
    stamp_duty_egp: float = Field(default=0.0, ge=0)

    total_government_duties_egp: float = Field(default=0.0, ge=0)

    # ── Seller Net ──
    seller_gross_receipt_egp: float = Field(default=0.0, ge=0)
    total_deductions_egp: float = Field(default=0.0, ge=0)
    seller_net_proceeds_egp: float = Field(default=0.0, ge=0)
    seller_effective_pct: float = Field(default=0.0, description="Seller keeps this % of gross")

    # ── Buyer Total Cost ──
    buyer_total_cost_egp: float = Field(default=0.0, ge=0)

    def compute(self) -> "TransactionFeeBreakdown":
        """
        Execute the full fee calculation cascade.

        The financial clearing sequence:
        1. Platform commission deducted from seller gross
        2. Scout fee deducted from seller gross (if applicable)
        3. Real Estate Disposal Tax calculated on transaction value
        4. Registration/Notary fees estimated on transaction value
        5. Stamp duty calculated on transaction value
        6. Seller net = gross - platform - scout - disposal_tax - registration - stamp
        7. Buyer total = transaction value + government duties + registration + stamp
        """
        tv = self.total_transaction_value_egp

        self.platform_commission_egp = round(tv * (self.platform_commission_pct / 100), 2)

        if self.scout_eligible:
            self.scout_fee_egp = round(tv * (self.scout_fee_pct / 100), 2)
        else:
            self.scout_fee_egp = 0.0

        self.real_estate_disposal_tax_egp = round(tv * (self.real_estate_disposal_tax_pct / 100), 2)
        self.registration_notary_fee_egp = round(tv * (self.registration_notary_fee_pct / 100), 2)
        self.stamp_duty_egp = round(tv * (self.stamp_duty_pct / 100), 2)

        self.total_government_duties_egp = round(
            self.real_estate_disposal_tax_egp
            + self.registration_notary_fee_egp
            + self.stamp_duty_egp,
            2,
        )

        self.seller_gross_receipt_egp = tv
        self.total_deductions_egp = round(
            self.platform_commission_egp
            + self.scout_fee_egp
            + self.real_estate_disposal_tax_egp
            + self.registration_notary_fee_egp
            + self.stamp_duty_egp,
            2,
        )
        self.seller_net_proceeds_egp = round(tv - self.total_deductions_egp, 2)

        if tv > 0:
            self.seller_effective_pct = round(
                (self.seller_net_proceeds_egp / tv) * 100, 2
            )

        self.buyer_total_cost_egp = round(
            tv + self.total_government_duties_egp, 2
        )

        return self


class LandLead(BaseModel):
    """
    A land lead submitted by a non-owner scout.

    Tracks the sourcing and legal verification workflow from
    initial submission through notary certification.
    """
    lead_id: str = Field(..., description="Unique lead identifier")
    land_id: Optional[str] = Field(default=None, description="Land record ID once verified and linked")
    scout_id: str = Field(..., description="Submitting scout user ID")
    scout_name: str = Field(default="", description="Scout display name")

    governorate: str = Field(default="")
    region_city: str = Field(default="")
    estimated_area_sqm: Optional[int] = Field(default=None, ge=0)
    estimated_price_per_sqm_egp: Optional[float] = Field(default=None, ge=0)
    soil_type: str = Field(default="")
    allowed_usage: str = Field(default="")
    nearest_highways: str = Field(default="")
    utilities_availability: str = Field(default="")
    description: str = Field(default="", description="Scout's notes on the land opportunity")

    legal_document_uploaded: bool = Field(
        default=False,
        description="Whether the scout has uploaded ownership/title documents",
    )
    document_upload_date: Optional[str] = Field(default=None)
    verified_by_notary: bool = Field(
        default=False,
        description="Whether the documents have been certified by Shahr Eqary (Notary)",
    )
    notary_verification_date: Optional[str] = Field(default=None)
    notary_reference_number: Optional[str] = Field(default=None, description="Shahr Eqary reference number")

    status: LeadStatus = Field(default=LeadStatus.SUBMITTED)
    rejection_reason: str = Field(default="")
    submitted_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
    )

    scout_fee_eligible: bool = Field(default=False, description="Whether scout earns a fee upon successful sale")
    scout_fee_pct: float = Field(default=1.5, ge=0, le=10)


class BrokerCommissionRecord(BaseModel):
    """
    Tracks broker commission for a specific land transaction.

    Implements the Winner-Takes-Commission Rule: only the broker
    who successfully brings the final buyer/investor and closes
    the deal receives the broker commission. The secondary assigned
    broker receives zero.
    """
    land_id: str = Field(..., description="Land parcel identifier")
    transaction_value_egp: float = Field(..., gt=0)
    broker_commission_pct: float = Field(default=1.5, ge=0, le=10, description="Negotiated commission percentage")
    allocated_brokers: List[Dict] = Field(
        default_factory=list,
        description="List of {broker_id, broker_name, is_winning, commission_egp, leads_generated, deals_closed}",
    )
    winning_broker_id: Optional[str] = Field(default=None, description="The broker who closed the deal")
    winning_broker_commission_egp: float = Field(default=0.0, ge=0)
    secondary_broker_id: Optional[str] = Field(default=None)
    secondary_broker_commission_egp: float = Field(default=0.0, description="Always zero per winner-takes-all rule")
    deal_closed: bool = Field(default=False)
    closed_date: Optional[str] = Field(default=None)
    buyer_id: Optional[str] = Field(default=None, description="Final buyer/investor who purchased")


class AdChannel(str, Enum):
    FACEBOOK = "Facebook"
    LINKEDIN = "LinkedIn"
    X_TWITTER = "X (Twitter)"
    GOOGLE_SEARCH = "Google Search"
    INSTAGRAM = "Instagram"
    SEO_META = "SEO Meta Tags"


class CampaignStatus(str, Enum):
    DRAFT = "Draft"
    ACTIVE = "Active"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class AdvertisingCampaign(BaseModel):
    """
    An advertising campaign for a land listing.

    Supports two paths:
    - Option A: AI Copilot Ad Generation (free/self-service)
    - Option B: Platform-Managed Funded Campaigns (paid)
    """
    campaign_id: str = Field(..., description="Unique campaign identifier")
    land_id: str = Field(..., description="Associated land parcel")
    seller_id: str = Field(default="", description="Owner who initiated the campaign")
    campaign_type: str = Field(
        default="ai_copilot",
        description="'ai_copilot' for free self-service, 'platform_managed' for paid",
    )
    status: CampaignStatus = Field(default=CampaignStatus.DRAFT)

    # Budget & Spending
    total_budget_egp: float = Field(default=0.0, ge=0, description="Total campaign budget in EGP")
    spent_egp: float = Field(default=0.0, ge=0, description="Total amount spent so far")
    platform_service_fee_pct: float = Field(default=5.0, ge=0, le=20, description="Platform fee on paid campaigns")
    delegated_to_broker_id: Optional[str] = Field(default=None, description="If seller delegates budget to a broker")

    # Channels
    target_channels: List[AdChannel] = Field(default_factory=list)
    target_audience: str = Field(default="", description="Audience targeting description")

    # Generated Content (Option A)
    generated_social_copy: Dict[str, str] = Field(
        default_factory=dict,
        description="Channel-specific marketing copy: {channel_name: copy_text}",
    )
    generated_seo_meta: Dict[str, str] = Field(
        default_factory=dict,
        description="SEO metadata: {title, description, keywords, og_title, og_description}",
    )

    # Performance Metrics
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    leads_generated: int = Field(default=0, ge=0)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())