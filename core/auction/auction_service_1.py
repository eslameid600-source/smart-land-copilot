"""
Smart Land Management Copilot — Auction & Marketplace Service
==============================================================
Dynamic Auction & Bidding Engine, Multi-Tiered Commission & Fees
Calculator, and Land Sourcing & Legal Verification Workflow.
"""

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from models.auction import (
    AuctionRecord, AuctionStatus, Bid, BidStatus,
    TransactionFeeBreakdown, LandLead, LeadStatus, ListingSource,
)

logger = logging.getLogger(__name__)


class AuctionEngine:
    """
    In-memory auction management engine.

    Manages the full auction lifecycle: creation, bid submission,
    bid validation, auto-outbidding, auction finalization, and
    winner determination. Designed for the Egyptian land market
    with configurable reserve prices and minimum bid increments.
    """

    def __init__(self):
        self._auctions: Dict[str, AuctionRecord] = {}
        self._bid_counter: Dict[str, int] = {}

    def create_auction(
        self,
        land_id: str,
        governorate: str,
        region_city: str,
        total_area_sqm: int,
        allowed_usage: str,
        base_price_egp: float,
        auction_end_date: Optional[str] = None,
        auction_start_date: Optional[str] = None,
        minimum_increment_pct: float = 2.0,
        reserve_price_egp: Optional[float] = None,
        listing_source: ListingSource = ListingSource.OWNER_DIRECT,
        scout_id: Optional[str] = None,
        scout_name: Optional[str] = None,
    ) -> AuctionRecord:
        """
        Create a new auction record and transition it to PENDING status.

        The auction will remain in PENDING until start_date is reached.
        If no start_date is provided, it transitions to LIVE immediately.
        """
        auction_id = f"AUC-{land_id}"

        base_per_sqm = round(base_price_egp / total_area_sqm, 2) if total_area_sqm > 0 else 0

        record = AuctionRecord(
            auction_id=auction_id,
            land_id=land_id,
            governorate=governorate,
            region_city=region_city,
            total_area_sqm=total_area_sqm,
            allowed_usage=allowed_usage,
            base_price_egp=base_price_egp,
            base_price_per_sqm_egp=base_per_sqm,
            auction_start_date=auction_start_date or datetime.now().isoformat(),
            auction_end_date=auction_end_date,
            minimum_increment_pct=minimum_increment_pct,
            reserve_price_egp=reserve_price_egp,
            listing_source=listing_source,
            scout_id=scout_id,
            scout_name=scout_name,
            status=AuctionStatus.PENDING,
        )

        if not auction_start_date or datetime.fromisoformat(auction_start_date) <= datetime.now():
            record.status = AuctionStatus.LIVE

        self._auctions[auction_id] = record
        self._bid_counter[auction_id] = 0
        logger.info(f"Created auction {auction_id} for land {land_id}, base={base_price_egp:,.0f} EGP")
        return record

    def place_bid(
        self,
        auction_id: str,
        bidder_id: str,
        bidder_name: str,
        bid_amount_egp: float,
        is_auto_bid: bool = False,
    ) -> Tuple[Optional[Bid], str]:
        """
        Validate and place a bid on a live auction.

        Returns (bid_record, error_message). If bid is valid,
        error_message is empty. Otherwise bid_record is None.
        """
        auction = self._auctions.get(auction_id)
        if not auction:
            return None, f"Auction {auction_id} not found"

        if auction.status != AuctionStatus.LIVE:
            return None, f"Auction is not live (status: {auction.status.value})"

        if not auction.is_auction_live():
            auction.status = AuctionStatus.ENDED
            self._finalize_auction(auction)
            return None, "Auction has ended"

        minimum = auction.compute_minimum_next_bid()
        if bid_amount_egp < minimum:
            return None, (
                f"Bid must be at least {minimum:,.0f} EGP "
                f"(current highest: {auction.current_highest_bid_egp:,.0f} EGP, "
                f"min increment: {auction.minimum_increment_pct}%)"
            )

        self._bid_counter[auction_id] += 1
        bid_id = f"BID-{auction_id}-{self._bid_counter[auction_id]:04d}"
        bid_per_sqm = round(bid_amount_egp / auction.total_area_sqm, 2) if auction.total_area_sqm > 0 else 0

        bid = Bid(
            bid_id=bid_id,
            auction_id=auction_id,
            bidder_id=bidder_id,
            bidder_name=bidder_name,
            bid_amount_egp=bid_amount_egp,
            bid_per_sqm_egp=bid_per_sqm,
            bid_timestamp=datetime.now().isoformat(),
            status=BidStatus.PENDING,
            is_auto_bid=is_auto_bid,
        )

        # Mark previous winning bid as OUTBID
        if auction.winning_bid:
            auction.winning_bid.status = BidStatus.OUTBID

        bid.status = BidStatus.WINNING
        auction.winning_bid = bid
        auction.current_highest_bid_egp = bid_amount_egp
        auction.current_highest_bid_per_sqm_egp = bid_per_sqm
        auction.bid_count += 1

        # Track unique bidders
        existing_bidders = {b.bidder_id for b in auction.all_bids}
        if bidder_id not in existing_bidders:
            auction.registered_bidders_count += 1

        auction.all_bids.append(bid)
        logger.info(
            f"Bid {bid_id}: {bidder_name} -> {bid_amount_egp:,.0f} EGP "
            f"on {auction_id} ({bid_per_sqm:,.2f} EGP/sqm)"
        )
        return bid, ""

    def register_bidder(self, auction_id: str, bidder_id: str, bidder_name: str) -> Optional[AuctionRecord]:
        """Register interest in an auction without placing a bid yet."""
        auction = self._auctions.get(auction_id)
        if not auction:
            return None
        existing = {b.bidder_id for b in auction.all_bids}
        if bidder_id not in existing:
            auction.registered_bidders_count += 1
        return auction

    def _finalize_auction(self, auction: AuctionRecord) -> None:
        """Determine winner and set final status."""
        auction.status = AuctionStatus.ENDED
        if auction.winning_bid:
            auction.winning_bid.status = BidStatus.WON
            # Check reserve price
            if auction.reserve_price_egp and auction.current_highest_bid_egp < auction.reserve_price_egp:
                logger.info(
                    f"Auction {auction.auction_id} ended below reserve "
                    f"({auction.current_highest_bid_egp:,.0f} < {auction.reserve_price_egp:,.0f})"
                )
            else:
                logger.info(
                    f"Auction {auction.auction_id} won by {auction.winning_bid.bidder_name} "
                    f"at {auction.current_highest_bid_egp:,.0f} EGP"
                )
        # Mark all other bids as LOST
        for b in auction.all_bids:
            if b.status == BidStatus.OUTBID:
                b.status = BidStatus.LOST
        if not auction.winning_bid:
            logger.info(f"Auction {auction.auction_id} ended with no bids")

    def close_auction(self, auction_id: str) -> Optional[AuctionRecord]:
        """Manually close an auction and finalize results."""
        auction = self._auctions.get(auction_id)
        if not auction:
            return None
        auction.status = AuctionStatus.ENDED
        self._finalize_auction(auction)
        return auction

    def cancel_auction(self, auction_id: str, reason: str = "") -> Optional[AuctionRecord]:
        """Cancel an auction."""
        auction = self._auctions.get(auction_id)
        if not auction:
            return None
        auction.status = AuctionStatus.CANCELLED
        for b in auction.all_bids:
            b.status = BidStatus.LOST
        auction.winning_bid = None
        logger.info(f"Auction {auction_id} cancelled: {reason}")
        return auction

    def get_auction(self, auction_id: str) -> Optional[AuctionRecord]:
        return self._auctions.get(auction_id)

    def get_auction_by_land(self, land_id: str) -> Optional[AuctionRecord]:
        for a in self._auctions.values():
            if a.land_id == land_id:
                return a
        return None

    def list_auctions(
        self,
        status: Optional[AuctionStatus] = None,
        governorate: Optional[str] = None,
        usage: Optional[str] = None,
    ) -> List[AuctionRecord]:
        """List auctions with optional filters."""
        results = list(self._auctions.values())
        if status:
            results = [a for a in results if a.status == status]
        if governorate:
            results = [a for a in results if a.governorate == governorate]
        if usage:
            results = [a for a in results if a.allowed_usage == usage]
        return results

    def get_bid_history(self, auction_id: str) -> List[Bid]:
        auction = self._auctions.get(auction_id)
        if not auction:
            return []
        return list(reversed(auction.all_bids))


class CommissionCalculator:
    """
    Multi-Tiered Commission & Fees Calculator.

    Automatically breaks down the total transactional value into
    explicit user-facing percentages for all parties, including
    Egyptian government duties (Real Estate Disposal Tax,
    Shahr Eqary registration/notary, and stamp duty).
    """

    DEFAULT_PLATFORM_PCT = 2.5
    DEFAULT_SCOUT_PCT = 1.5
    DISPOSAL_TAX_PCT = 2.5
    REGISTRATION_NOTARY_PCT = 3.0
    STAMP_DUTY_PCT = 0.5

    @classmethod
    def compute_breakdown(
        cls,
        total_value_egp: float,
        land_id: str = "",
        auction_id: Optional[str] = None,
        is_auction: bool = False,
        scout_name: str = "",
        scout_eligible: bool = False,
        custom_platform_pct: Optional[float] = None,
        custom_scout_pct: Optional[float] = None,
    ) -> TransactionFeeBreakdown:
        """
        Calculate the full financial clearing for a transaction.

        Parameters
        ----------
        total_value_egp       : Final sale price or winning bid in EGP
        land_id               : Land record identifier
        auction_id            : Auction identifier if applicable
        is_auction            : Whether this is an auction transaction
        scout_name            : Name of the scout/sourcing agent
        scout_eligible        : Whether scout fee should be applied
        custom_platform_pct   : Override default platform commission %
        custom_scout_pct      : Override default scout fee %
        """
        breakdown = TransactionFeeBreakdown(
            land_id=land_id,
            auction_id=auction_id,
            total_transaction_value_egp=total_value_egp,
            transaction_type="Auction" if is_auction else "Direct Sale",
            platform_commission_pct=custom_platform_pct or cls.DEFAULT_PLATFORM_PCT,
            scout_fee_pct=custom_scout_pct or cls.DEFAULT_SCOUT_PCT,
            scout_name=scout_name,
            scout_eligible=scout_eligible,
            real_estate_disposal_tax_pct=cls.DISPOSAL_TAX_PCT,
            registration_notary_fee_pct=cls.REGISTRATION_NOTARY_PCT,
            stamp_duty_pct=cls.STAMP_DUTY_PCT,
        )
        breakdown.compute()
        return breakdown

    @classmethod
    def compute_for_auction(cls, auction: AuctionRecord) -> TransactionFeeBreakdown:
        """Convenience method: compute breakdown from an AuctionRecord."""
        sale_value = auction.current_highest_bid_egp if auction.current_highest_bid_egp > 0 else auction.base_price_egp
        return cls.compute_breakdown(
            total_value_egp=sale_value,
            land_id=auction.land_id,
            auction_id=auction.auction_id,
            is_auction=True,
            scout_name=auction.scout_name or "",
            scout_eligible=auction.listing_source == ListingSource.SCOUT_SOURCED,
        )

    @classmethod
    def compute_for_direct_sale(
        cls,
        land: Dict,
        scout_name: str = "",
        scout_eligible: bool = False,
    ) -> TransactionFeeBreakdown:
        """Convenience method: compute breakdown from a raw land dict."""
        sale_value = land["Total_Area_Sqm"] * land["Price_Per_Sqm_EGP"]
        return cls.compute_breakdown(
            total_value_egp=sale_value,
            land_id=land["Land_ID"],
            is_auction=False,
            scout_name=scout_name,
            scout_eligible=scout_eligible,
        )

    @classmethod
    def format_breakdown_table(cls, breakdown: TransactionFeeBreakdown) -> List[Dict]:
        """
        Format the breakdown as a list of dicts suitable for
        Streamlit st.dataframe or pandas DataFrame conversion.
        """
        rows = [
            {
                "Party / Item": "SELLER — Gross Receipt",
                "Rate": "100.00%",
                "Amount (EGP)": f"{breakdown.seller_gross_receipt_egp:,.2f}",
                "Notes": "Full transaction value",
            },
            {
                "Party / Item": "  (-) Platform Commission",
                "Rate": f"-{breakdown.platform_commission_pct:.1f}%",
                "Amount (EGP)": f"-{breakdown.platform_commission_egp:,.2f}",
                "Notes": "Marketplace transaction fee",
            },
        ]
        if breakdown.scout_eligible and breakdown.scout_fee_egp > 0:
            rows.append({
                "Party / Item": f"  (-) Scout Fee ({breakdown.scout_name})",
                "Rate": f"-{breakdown.scout_fee_pct:.1f}%",
                "Amount (EGP)": f"-{breakdown.scout_fee_egp:,.2f}",
                "Notes": "Sourcing agent discovery fee",
            })
        rows.extend([
            {
                "Party / Item": "  (-) Real Estate Disposal Tax",
                "Rate": f"-{breakdown.real_estate_disposal_tax_pct:.1f}%",
                "Amount (EGP)": f"-{breakdown.real_estate_disposal_tax_egp:,.2f}",
                "Notes": "\u0636\u0631\u064a\u0628\u0629 \u0627\u0644\u062a\u0635\u0631\u0641\u0627\u062a \u0627\u0644\u0639\u0642\u0627\u0631\u064a\u0629",
            },
            {
                "Party / Item": "  (-) Registration / Notary Fees",
                "Rate": f"-{breakdown.registration_notary_fee_pct:.1f}%",
                "Amount (EGP)": f"-{breakdown.registration_notary_fee_egp:,.2f}",
                "Notes": "\u0627\u0644\u0634\u0647\u0631 \u0627\u0644\u0639\u0642\u0627\u0631\u064a + \u0627\u0644\u0645\u0648\u062b\u0642 \u0627\u0644\u0639\u0645\u0648\u0645\u064a",
            },
            {
                "Party / Item": "  (-) Stamp Duty",
                "Rate": f"-{breakdown.stamp_duty_pct:.1f}%",
                "Amount (EGP)": f"-{breakdown.stamp_duty_egp:,.2f}",
                "Notes": "\u0648\u0627\u062c\u0628\u0629 \u0627\u0644\u062e\u062a\u0645",
            },
            {
                "Party / Item": "SELLER — Net Proceeds",
                "Rate": f"{breakdown.seller_effective_pct:.2f}%",
                "Amount (EGP)": f"{breakdown.seller_net_proceeds_egp:,.2f}",
                "Notes": "Effective seller take-home",
            },
            {
                "Party / Item": "---",
                "Rate": "---",
                "Amount (EGP)": "---",
                "Notes": "---",
            },
            {
                "Party / Item": "BUYER — Total Cost",
                "Rate": "",
                "Amount (EGP)": f"{breakdown.buyer_total_cost_egp:,.2f}",
                "Notes": "Transaction value + all government duties",
            },
            {
                "Party / Item": "  (+) Transaction Value",
                "Rate": "",
                "Amount (EGP)": f"{breakdown.total_transaction_value_egp:,.2f}",
                "Notes": "",
            },
            {
                "Party / Item": "  (+) Total Government Duties",
                "Rate": f"{(breakdown.real_estate_disposal_tax_pct + breakdown.registration_notary_fee_pct + breakdown.stamp_duty_pct):.1f}%",
                "Amount (EGP)": f"+{breakdown.total_government_duties_egp:,.2f}",
                "Notes": "Disposal Tax + Registration + Stamp Duty",
            },
        ])
        return rows


class LandSourcingService:
    """
    Land Sourcing & Legal Verification Workflow.

    Manages the scout-mode workflow where non-owners can submit land leads,
    upload legal documents, and track notary/Shahr Eqary verification status.
    """

    def __init__(self):
        self._leads: Dict[str, LandLead] = {}

    def submit_lead(
        self,
        scout_id: str,
        scout_name: str,
        governorate: str,
        region_city: str,
        estimated_area_sqm: Optional[int],
        estimated_price_per_sqm_egp: Optional[float],
        soil_type: str = "",
        allowed_usage: str = "",
        nearest_highways: str = "",
        utilities_availability: str = "",
        description: str = "",
    ) -> LandLead:
        """Submit a new land lead in Scout Mode."""
        lead_id = f"LEAD-{uuid.uuid4().hex[:8].upper()}"
        lead = LandLead(
            lead_id=lead_id,
            scout_id=scout_id,
            scout_name=scout_name,
            governorate=governorate,
            region_city=region_city,
            estimated_area_sqm=estimated_area_sqm,
            estimated_price_per_sqm_egp=estimated_price_per_sqm_egp,
            soil_type=soil_type,
            allowed_usage=allowed_usage,
            nearest_highways=nearest_highways,
            utilities_availability=utilities_availability,
            description=description,
            status=LeadStatus.SUBMITTED,
            scout_fee_eligible=False,
        )
        self._leads[lead_id] = lead
        logger.info(f"Land lead {lead_id} submitted by scout {scout_name}")
        return lead

    def upload_legal_documents(
        self,
        lead_id: str,
        land_id: Optional[str] = None,
    ) -> Optional[LandLead]:
        """
        Mark legal documents as uploaded for a lead.
        Optionally link to an existing land record in the database.
        """
        lead = self._leads.get(lead_id)
        if not lead:
            return None
        lead.legal_document_uploaded = True
        lead.document_upload_date = datetime.now().isoformat()
        lead.status = LeadStatus.DOCUMENTS_UPLOADED
        if land_id:
            lead.land_id = land_id
        logger.info(f"Legal documents uploaded for lead {lead_id}")
        return lead

    def verify_with_notary(
        self,
        lead_id: str,
        notary_reference_number: str = "",
    ) -> Optional[LandLead]:
        """
        Mark a lead as verified by Notary / Shahr Eqary.
        Upon successful verification, the lead becomes eligible for
        scout fee upon successful sale.
        """
        lead = self._leads.get(lead_id)
        if not lead:
            return None
        if not lead.legal_document_uploaded:
            logger.warning(f"Cannot verify lead {lead_id}: documents not yet uploaded")
            return lead
        lead.verified_by_notary = True
        lead.notary_verification_date = datetime.now().isoformat()
        lead.notary_reference_number = notary_reference_number
        lead.status = LeadStatus.NOTARY_VERIFIED
        lead.scout_fee_eligible = True
        logger.info(
            f"Lead {lead_id} verified by Notary (ref: {notary_reference_number}), "
            f"scout fee eligible for {lead.scout_name}"
        )
        return lead

    def reject_lead(self, lead_id: str, reason: str) -> Optional[LandLead]:
        """Reject a lead with a reason."""
        lead = self._leads.get(lead_id)
        if not lead:
            return None
        lead.status = LeadStatus.REJECTED
        lead.rejection_reason = reason
        logger.info(f"Lead {lead_id} rejected: {reason}")
        return lead

    def get_lead(self, lead_id: str) -> Optional[LandLead]:
        return self._leads.get(lead_id)

    def list_leads(
        self,
        scout_id: Optional[str] = None,
        status: Optional[LeadStatus] = None,
    ) -> List[LandLead]:
        """List leads with optional filters."""
        results = list(self._leads.values())
        if scout_id:
            results = [l for l in results if l.scout_id == scout_id]
        if status:
            results = [l for l in results if l.status == status]
        return results

    def get_lead_stats(self) -> Dict:
        """Return summary statistics for all leads."""
        leads = list(self._leads.values())
        return {
            "total_leads": len(leads),
            "submitted": sum(1 for l in leads if l.status == LeadStatus.SUBMITTED),
            "documents_uploaded": sum(1 for l in leads if l.status == LeadStatus.DOCUMENTS_UPLOADED),
            "notary_verified": sum(1 for l in leads if l.status == LeadStatus.NOTARY_VERIFIED),
            "rejected": sum(1 for l in leads if l.status == LeadStatus.REJECTED),
            "scout_fee_eligible": sum(1 for l in leads if l.scout_fee_eligible),
        }


# ────────────────────────────────────────────────────────────
# Singletons
# ────────────────────────────────────────────────────────────

_auction_engine: Optional[AuctionEngine] = None
_sourcing_service: Optional[LandSourcingService] = None


def get_auction_engine() -> AuctionEngine:
    global _auction_engine
    if _auction_engine is None:
        _auction_engine = AuctionEngine()
        _initialize_sample_auctions(_auction_engine)
    return _auction_engine


def get_sourcing_service() -> LandSourcingService:
    global _sourcing_service
    if _sourcing_service is None:
        _sourcing_service = LandSourcingService()
        _initialize_sample_leads(_sourcing_service)
    return _sourcing_service


def _initialize_sample_auctions(engine: AuctionEngine) -> None:
    """Seed the auction engine with sample data from auction-eligible land records."""
    from data.land_database import get_all_lands
    lands = get_all_lands()
    for land in lands:
        if land["Investment_Status"] == "Public Auction":
            starting_total = land.get("Starting_Price_Per_Sqm_EGP", land["Price_Per_Sqm_EGP"]) * land["Total_Area_Sqm"]
            auction = engine.create_auction(
                land_id=land["Land_ID"],
                governorate=land["Governorate"],
                region_city=land["Region_City"],
                total_area_sqm=land["Total_Area_Sqm"],
                allowed_usage=land["Allowed_Usage"],
                base_price_egp=starting_total,
                auction_end_date=land.get("Auction_Date"),
                minimum_increment_pct=2.0,
                reserve_price_egp=round(starting_total * 1.15, 2),
            )
            # Place some sample bids to simulate activity
            engine.register_bidder(auction.auction_id, "INV-001", "Al-Ahly Capital Fund")
            engine.register_bidder(auction.auction_id, "INV-002", "Gulf Real Estate Holdings")
            engine.register_bidder(auction.auction_id, "INV-003", "Nile Valley Investments")
            auction.registered_bidders_count = 3

            # Simulate 1-2 bids
            first_bid = round(starting_total * 1.04, 2)
            engine.place_bid(auction.auction_id, "INV-001", "Al-Ahly Capital Fund", first_bid)

            second_bid = round(first_bid * 1.025, 2)
            engine.place_bid(auction.auction_id, "INV-002", "Gulf Real Estate Holdings", second_bid)


def _initialize_sample_leads(service: LandSourcingService) -> None:
    """Seed the sourcing service with sample scout-submitted leads."""
    service.submit_lead(
        scout_id="SCOUT-005",
        scout_name="Ahmed Mansour",
        governorate="Suez",
        region_city="Ain Sokhna Industrial Zone",
        estimated_area_sqm=75_000,
        estimated_price_per_sqm_egp=2_200,
        soil_type="Sandy limestone",
        allowed_usage="Industrial",
        nearest_highways="Cairo-Sokhna Road, Galala Mountain Road",
        utilities_availability="Water, Electricity",
        description="Industrial zone expansion parcel near Sokhna port. Owner is a retiring factory owner looking to liquidate. Strong container logistics potential.",
    )
    service.upload_legal_documents("LEAD-00000001", land_id=None)

    service.submit_lead(
        scout_id="SCOUT-007",
        scout_name="Fatma Hassan",
        governorate="Ismailia",
        region_city="Ismailia City West",
        estimated_area_sqm=40_000,
        estimated_price_per_sqm_egp=4_500,
        soil_type="Sandy clay",
        allowed_usage="Logistics",
        nearest_highways="Ismailia-Cairo Agricultural Road",
        utilities_availability="Water, Electricity, Gas",
        description="Prime logistics site adjacent to the Suez Canal corridor. Suitable for bonded warehouse development. Existing road access is excellent.",
    )