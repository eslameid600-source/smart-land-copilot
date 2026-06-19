"""
Smart Land Management Copilot — User Account Service
=====================================================
Multi-role account management, broker document validation,
and role-based access control enforcement.
"""
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional
from models.models.user import UserAccount, UserRole, BrokerVerificationStatus, DocumentType, BrokerDocument
logger = logging.getLogger(__name__)

class UserService:
    """
    In-memory user account management service.

    Handles account creation, role switching, broker verification
    workflows, and access control enforcement.
    """
    REQUIRED_BROKER_DOCUMENT_TYPES = [DocumentType.BROKERAGE_LICENSE, DocumentType.FINANCIAL_GUARANTEE]

    def __init__(self):
        self._users: Dict[str, UserAccount] = {}

    def create_account(self, full_name: str, role: UserRole, email: str='', phone: str='', company_name: str='', **kwargs) -> UserAccount:
        """Create a new user account with the specified role."""
        user_id = f'USR-{uuid.uuid4().hex[:8].upper()}'
        user = UserAccount(user_id=user_id, full_name=full_name, email=email, phone=phone, role=role, company_name=company_name, **kwargs)
        if role == UserRole.CERTIFIED_BROKER:
            user.broker_verification_status = BrokerVerificationStatus.PENDING_VERIFICATION
        self._users[user_id] = user
        logger.info(f'Created {role.value} account {user_id}: {full_name}')
        return user

    def get_user(self, user_id: str) -> Optional[UserAccount]:
        return self._users.get(user_id)

    def list_users(self, role: Optional[UserRole]=None, is_active: bool=True) -> List[UserAccount]:
        """List users with optional role and active status filters."""
        results = list(self._users.values())
        if role:
            results = [u for u in results if u.role == role]
        if is_active is not None:
            results = [u for u in results if u.is_active == is_active]
        return results

    def update_user(self, user_id: str, **updates) -> Optional[UserAccount]:
        """Update user fields."""
        user = self._users.get(user_id)
        if not user:
            return None
        for field, value in updates.items():
            if hasattr(user, field):
                setattr(user, field, value)
        return user

    def deactivate_user(self, user_id: str) -> Optional[UserAccount]:
        user = self._users.get(user_id)
        if not user:
            return None
        user.is_active = False
        return user

    def submit_broker_document(self, broker_id: str, document_type: DocumentType, document_name: str='') -> Optional[BrokerDocument]:
        """
        Submit a document for broker verification.
        Returns the created BrokerDocument or None if user not found / not a broker.
        """
        user = self._users.get(broker_id)
        if not user or user.role != UserRole.CERTIFIED_BROKER:
            return None
        doc = BrokerDocument(document_id=f'DOC-{uuid.uuid4().hex[:8].upper()}', document_type=document_type, document_name=document_name, upload_date=datetime.now().isoformat(), verified=False)
        user.broker_documents.append(doc)
        logger.info(f'Document {doc.document_id} ({document_type.value}) submitted for broker {broker_id}')
        self._check_broker_verification_readiness(broker_id)
        return doc

    def verify_broker_document(self, broker_id: str, document_id: str, approved: bool, rejection_reason: str='') -> Optional[UserAccount]:
        """Admin action: approve or reject a broker document."""
        user = self._users.get(broker_id)
        if not user or user.role != UserRole.CERTIFIED_BROKER:
            return None
        for doc in user.broker_documents:
            if doc.document_id == document_id:
                doc.verified = approved
                doc.verification_date = datetime.now().isoformat()
                if not approved:
                    doc.rejection_reason = rejection_reason
                break
        self._check_broker_verification_readiness(broker_id)
        return user

    def _check_broker_verification_readiness(self, broker_id: str) -> None:
        """
        Check if all required documents have been verified.
        If so, automatically promote broker to Verified status.
        """
        user = self._users.get(broker_id)
        if not user:
            return
        submitted_types = {doc.document_type for doc in user.broker_documents}
        verified_types = {doc.document_type for doc in user.broker_documents if doc.verified}
        required = set(self.REQUIRED_BROKER_DOCUMENT_TYPES)
        if required.issubset(submitted_types) and required.issubset(verified_types):
            user.broker_verification_status = BrokerVerificationStatus.VERIFIED
            logger.info(f'Broker {broker_id} ({user.full_name}) is now VERIFIED')
        elif any((not doc.verified for doc in user.broker_documents)):
            has_rejection = any((doc.rejection_reason for doc in user.broker_documents if not doc.verified and doc.document_type in required))
            if has_rejection:
                user.broker_verification_status = BrokerVerificationStatus.REJECTED

    def get_broker_verification_status(self, broker_id: str) -> Optional[Dict]:
        """Return detailed verification status for a broker."""
        user = self._users.get(broker_id)
        if not user or user.role != UserRole.CERTIFIED_BROKER:
            return None
        required = set(self.REQUIRED_BROKER_DOCUMENT_TYPES)
        docs = user.broker_documents
        submitted_types = {d.document_type for d in docs}
        verified_types = {d.document_type for d in docs if d.verified}
        return {'broker_id': broker_id, 'broker_name': user.full_name, 'status': user.broker_verification_status.value, 'required_documents': [t.value for t in required], 'submitted': [t.value for t in submitted_types], 'verified': [t.value for t in verified_types], 'missing': [t.value for t in required - submitted_types], 'pending_verification': [t.value for t in submitted_types - verified_types], 'can_access_dashboard': user.can_access_dashboard, 'can_manage_listings': user.can_manage_listings, 'documents': [{'document_id': d.document_id, 'type': d.document_type.value, 'name': d.document_name, 'uploaded': d.upload_date[:10] if d.upload_date else '', 'verified': d.verified, 'verified_date': d.verification_date[:10] if d.verification_date else '', 'rejection_reason': d.rejection_reason} for d in docs]}

    def add_to_watchlist(self, user_id: str, land_id: str) -> Optional[UserAccount]:
        user = self._users.get(user_id)
        if not user or user.role != UserRole.BUYER_INVESTOR:
            return None
        if land_id not in user.watchlist_land_ids:
            user.watchlist_land_ids.append(land_id)
        return user

    def remove_from_watchlist(self, user_id: str, land_id: str) -> Optional[UserAccount]:
        user = self._users.get(user_id)
        if not user:
            return None
        if land_id in user.watchlist_land_ids:
            user.watchlist_land_ids.remove(land_id)
        return user

    def add_to_portfolio(self, user_id: str, land_id: str) -> Optional[UserAccount]:
        user = self._users.get(user_id)
        if not user or user.role != UserRole.BUYER_INVESTOR:
            return None
        if land_id not in user.portfolio_land_ids:
            user.portfolio_land_ids.append(land_id)
        return user

    def register_owned_land(self, user_id: str, land_id: str) -> Optional[UserAccount]:
        user = self._users.get(user_id)
        if not user or user.role != UserRole.SELLER_OWNER:
            return None
        if land_id not in user.owned_land_ids:
            user.owned_land_ids.append(land_id)
        return user

    def assign_land_to_broker(self, user_id: str, land_id: str) -> Optional[UserAccount]:
        user = self._users.get(user_id)
        if not user or user.role != UserRole.CERTIFIED_BROKER:
            return None
        if not user.is_broker_verified:
            return None
        if land_id not in user.assigned_land_ids:
            user.assigned_land_ids.append(land_id)
        return user

    def record_broker_deal(self, broker_id: str, commission_egp: float) -> Optional[UserAccount]:
        """Record a closed deal and commission for a broker."""
        user = self._users.get(broker_id)
        if not user or user.role != UserRole.CERTIFIED_BROKER:
            return None
        user.total_deals_closed += 1
        user.total_commission_earned_egp += commission_egp
        if user.assigned_land_ids:
            active_count = len(user.assigned_land_ids)
            user.performance_score = round(min(100.0, user.total_deals_closed / max(active_count, 1) * 50 + user.total_commission_earned_egp / 1000000 * 10), 2)
        return user

    def get_user_count_by_role(self) -> Dict[str, int]:
        counts = {}
        for role in UserRole:
            counts[role.value] = sum((1 for u in self._users.values() if u.role == role))
        return counts
_user_service: Optional[UserService] = None

def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService()
        _seed_sample_users(_user_service)
    return _user_service

def reset_user_service() -> None:
    global _user_service
    _user_service = None

def _seed_sample_users(svc: UserService) -> None:
    """Seed the service with sample user accounts for demonstration."""
    buyer = svc.create_account(full_name='Karim El-Masry', role=UserRole.BUYER_INVESTOR, email='karim@nilecap.eg', phone='+201012345678', company_name='Nile Capital Partners', investment_budget_max_egp=500000000, preferred_usages=['Industrial', 'Logistics'], preferred_governorates=['Cairo', 'Suez', 'Ismailia'])
    svc.add_to_watchlist(buyer.user_id, 'EG-CAI-01')
    svc.add_to_watchlist(buyer.user_id, 'EG-SUZ-01')
    seller = svc.create_account(full_name='Nadia Fawzy', role=UserRole.SELLER_OWNER, email='nadia@gulfreal.eg', phone='+201098765432', company_name='Gulf Real Estate Holdings')
    svc.register_owned_land(seller.user_id, 'EG-CAI-01')
    broker = svc.create_account(full_name='Omar Abdel-Rahim', role=UserRole.CERTIFIED_BROKER, email='omar@certifiedbroker.eg', phone='+201155544433', company_name='Abdel-Rahim Real Estate', broker_license_number='BROK-EG-2024-0447', broker_specializations=['Industrial', 'Logistics', 'Commercial'])
    doc1 = svc.submit_broker_document(broker.user_id, DocumentType.BROKERAGE_LICENSE, 'broker_license_2024.pdf')
    doc2 = svc.submit_broker_document(broker.user_id, DocumentType.FINANCIAL_GUARANTEE, 'bank_guarantee_500k.pdf')
    if doc1:
        svc.verify_broker_document(broker.user_id, doc1.document_id, approved=True)
    if doc2:
        svc.verify_broker_document(broker.user_id, doc2.document_id, approved=True)
    svc.create_account(full_name='Hassan Ibrahim', role=UserRole.CERTIFIED_BROKER, email='hassan@realestate.eg', phone='+201234567890', company_name='Ibrahim Properties', broker_license_number='BROK-EG-2024-0891', broker_specializations=['Residential', 'Commercial'])