"""models.auction — facade with auction-related dataclasses."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class BrokerAllocation:
    """A broker allocation record for an auction."""

    auction_id: str
    broker_id: str
    land_id: str
    commission_pct: float = 2.5
    assigned_at: Optional[datetime] = None


@dataclass
class BrokerCommissionRecord:
    """A broker commission record produced after a sale."""

    broker_id: str
    land_id: str
    sale_amount_egp: float = 0.0
    commission_rate_pct: float = 2.5
    net_commission_egp: float = 0.0
    paid: bool = False
    paid_at: Optional[datetime] = None


@dataclass
class Auction:
    """A land auction."""

    auction_id: str
    land_id: str
    starting_price_egp: float = 0.0
    highest_bid: float = 0.0
    highest_bidder_id: Optional[str] = None
    status: str = "open"
    bidders: List[str] = field(default_factory=list)


__all__ = ["BrokerAllocation", "BrokerCommissionRecord", "Auction"]
