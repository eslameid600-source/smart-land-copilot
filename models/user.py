"""models.user — facade with user-related dataclasses and enums."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any, Dict, List, Optional


class UserRole(str, PyEnum):
    BUYER_INVESTOR = "Buyer/Investor"
    SELLER_OWNER = "Seller/Owner"
    CERTIFIED_BROKER = "Certified Broker"
    ADMIN = "Admin"


class DocumentType(str, PyEnum):
    OWNERSHIP_DEED = "ownership_deed"
    CONTRACT = "contract"
    TAX_RECEIPT = "tax_receipt"
    ID_CARD = "id_card"
    COMMERCIAL_REGISTER = "commercial_register"
    OTHER = "other"


class BrokerVerificationStatus(str, PyEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass
class BrokerDocument:
    """A document submitted by a broker for verification."""

    doc_id: str
    broker_id: str
    document_type: DocumentType = DocumentType.OTHER
    file_path: str = ""
    verified: bool = False
    uploaded_at: Optional[datetime] = None


@dataclass
class UserAccount:
    """Canonical user-account record used by UI / service layers."""

    user_id: str
    full_name: str = ""
    email: Optional[str] = None
    phone_number: Optional[str] = None
    role: UserRole = UserRole.BUYER_INVESTOR
    status: str = "active"
    password_hash: str = ""
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "full_name": self.full_name,
            "email": self.email,
            "phone_number": self.phone_number,
            "role": self.role.value,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class BuyerProfile:
    """Investor-side profile for matchmaking.

    Includes legacy fields used by api/routes/search_engine.py:
    buyer_id, company_name, total_projects_executed,
    largest_project_value_egp, total_acquisition_value_egp.
    """

    user_id: str = ""
    budget_max_egp: float = 0.0
    preferred_governorates: List[str] = field(default_factory=list)
    preferred_usages: List[str] = field(default_factory=list)
    watchlist: List[str] = field(default_factory=list)

    # Legacy / extended fields
    buyer_id: str = ""
    company_name: str = ""
    total_projects_executed: int = 0
    largest_project_value_egp: float = 0.0
    total_acquisition_value_egp: float = 0.0

    def classify(self) -> str:
        """Classify the buyer into a tier based on acquisition history."""
        if self.total_acquisition_value_egp > 50_000_000:
            return "enterprise"
        if self.total_acquisition_value_egp > 10_000_000:
            return "growth"
        if self.total_acquisition_value_egp > 0:
            return "starter"
        return "new"


@dataclass
class SellerProfile:
    """Landowner-side profile for matchmaking."""

    user_id: str
    total_lands_listed: int = 0
    total_sales_egp: float = 0.0
    default_commission_pct: float = 2.5


@dataclass
class InvestorCriteria:
    """Investor search criteria."""

    budget_max_egp: Optional[float] = None
    governorates: List[str] = field(default_factory=list)
    usages: List[str] = field(default_factory=list)
    min_area_sqm: Optional[int] = None
    max_area_sqm: Optional[int] = None


@dataclass
class MatchResult:
    """A single matchmaking result."""

    land_id: str
    investor_id: str
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)


__all__ = [
    "UserRole",
    "DocumentType",
    "BrokerVerificationStatus",
    "BrokerDocument",
    "UserAccount",
    "BuyerProfile",
    "SellerProfile",
    "InvestorCriteria",
    "MatchResult",
]
