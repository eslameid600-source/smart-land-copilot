"""
Smart Land Management Copilot — Broker Delegation Service
=========================================================
Dual-Broker listing allocation, performance tracking,
and Winner-Takes-Commission ledger logic.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from models.auction import BrokerCommissionRecord
from models.land import BrokerAllocation

logger = logging.getLogger(__name__)

class BrokerDelegationService:
    """
    Manages dual-broker listing allocation and the
    Winner-Takes-Commission Rule for land transactions.

    Business Rules:
    - A Seller/Owner can delegate a land to a maximum of 2 verified brokers.
    - Performance metrics are tracked per broker per listing.
    - Upon deal closure, only the broker who brought the final buyer
      receives the commission. The secondary broker receives zero.
    """
    MAX_BROKERS_PER_LAND = 2

    def __init__(self):
        self._land_brokers: Dict[str, List[BrokerAllocation]] = {}
        self._commission_ledger: Dict[str, BrokerCommissionRecord] = {}

    def allocate_broker(self, land_id: str, broker_id: str, broker_name: str='') -> Tuple[Optional[BrokerAllocation], str]:
        """
        Allocate a verified broker to a land listing.

        Enforces the maximum 2-broker rule.
        Returns (allocation, error_message).
        """
        current = self._land_brokers.get(land_id, [])
        if len(current) >= self.MAX_BROKERS_PER_LAND:
            existing_names = [b.broker_name or b.broker_id for b in current]
            return (None, f"Maximum {self.MAX_BROKERS_PER_LAND} brokers already allocated to {land_id}: {', '.join(existing_names)}")
        for b in current:
            if b.broker_id == broker_id:
                return (None, f'Broker {broker_id} is already allocated to {land_id}')
        allocation = BrokerAllocation(broker_id=broker_id, broker_name=broker_name, assigned_date=datetime.now().isoformat())
        current.append(allocation)
        self._land_brokers[land_id] = current
        logger.info(f'Allocated broker {broker_name} ({broker_id}) to land {land_id} ({len(current)}/{self.MAX_BROKERS_PER_LAND})')
        return (allocation, '')

    def remove_broker(self, land_id: str, broker_id: str) -> bool:
        """Remove a broker allocation from a land listing."""
        current = self._land_brokers.get(land_id, [])
        filtered = [b for b in current if b.broker_id != broker_id]
        if len(filtered) == len(current):
            return False
        self._land_brokers[land_id] = filtered
        logger.info(f'Removed broker {broker_id} from land {land_id}')
        return True

    def get_land_brokers(self, land_id: str) -> List[BrokerAllocation]:
        """Get all brokers allocated to a specific land."""
        return list(self._land_brokers.get(land_id, []))

    def record_broker_lead(self, land_id: str, broker_id: str) -> None:
        """Increment the lead counter for a broker on a specific land."""
        for allocation in self._land_brokers.get(land_id, []):
            if allocation.broker_id == broker_id:
                allocation.leads_generated += 1
                return

    def close_deal(self, land_id: str, winning_broker_id: str, buyer_id: str, transaction_value_egp: float, broker_commission_pct: float=1.5) -> Optional[BrokerCommissionRecord]:
        """
        Close a deal and execute the Winner-Takes-Commission Rule.

        Only the broker who brought the final buyer receives the full
        commission. The secondary broker receives zero commission.
        """
        allocations = self._land_brokers.get(land_id, [])
        winning_broker = None
        secondary_broker = None
        for alloc in allocations:
            if alloc.broker_id == winning_broker_id:
                alloc.deals_closed += 1
                alloc.is_winning_broker = True
                winning_broker = alloc
            else:
                secondary_broker = alloc
        winning_commission = round(transaction_value_egp * (broker_commission_pct / 100), 2)
        broker_list = []
        if winning_broker:
            winning_broker.commission_earned_egp += winning_commission
            broker_list.append({'broker_id': winning_broker.broker_id, 'broker_name': winning_broker.broker_name, 'is_winning': True, 'commission_egp': winning_commission, 'leads_generated': winning_broker.leads_generated, 'deals_closed': winning_broker.deals_closed})
        if secondary_broker:
            broker_list.append({'broker_id': secondary_broker.broker_id, 'broker_name': secondary_broker.broker_name, 'is_winning': False, 'commission_egp': 0.0, 'leads_generated': secondary_broker.leads_generated, 'deals_closed': secondary_broker.deals_closed})
        record = BrokerCommissionRecord(land_id=land_id, transaction_value_egp=transaction_value_egp, broker_commission_pct=broker_commission_pct, allocated_brokers=broker_list, winning_broker_id=winning_broker_id, winning_broker_commission_egp=winning_commission, secondary_broker_id=secondary_broker.broker_id if secondary_broker else None, secondary_broker_commission_egp=0.0, deal_closed=True, closed_date=datetime.now().isoformat(), buyer_id=buyer_id)
        self._commission_ledger[land_id] = record
        logger.info(f'Deal closed for {land_id}: Winner={winning_broker_id}, Commission={winning_commission:,.0f} EGP, Secondary=0 EGP')
        return record

    def get_commission_record(self, land_id: str) -> Optional[BrokerCommissionRecord]:
        return self._commission_ledger.get(land_id)

    def get_all_commission_records(self) -> List[BrokerCommissionRecord]:
        return list(self._commission_ledger.values())

    def get_broker_performance_summary(self, broker_id: str) -> Dict:
        """Aggregate performance metrics for a specific broker across all lands."""
        total_leads = 0
        total_deals = 0
        total_commission = 0.0
        lands_assigned = 0
        lands_won = 0
        for land_id, allocations in self._land_brokers.items():
            for alloc in allocations:
                if alloc.broker_id == broker_id:
                    lands_assigned += 1
                    total_leads += alloc.leads_generated
                    total_deals += alloc.deals_closed
                    total_commission += alloc.commission_earned_egp
                    if alloc.is_winning_broker:
                        lands_won += 1
        return {'broker_id': broker_id, 'lands_assigned': lands_assigned, 'total_leads_generated': total_leads, 'total_deals_closed': total_deals, 'lands_won': lands_won, 'total_commission_earned_egp': total_commission, 'win_rate_pct': round(lands_won / max(lands_assigned, 1) * 100, 1)}
_broker_delegation_service: Optional[BrokerDelegationService] = None

def get_broker_delegation_service() -> BrokerDelegationService:
    global _broker_delegation_service
    if _broker_delegation_service is None:
        _broker_delegation_service = BrokerDelegationService()
        _seed_sample_delegations(_broker_delegation_service)
    return _broker_delegation_service

def _seed_sample_delegations(svc: BrokerDelegationService) -> None:
    """Seed with sample broker delegations for demonstration."""
    from services.user_service import get_user_service
    us = get_user_service()
    brokers = [u for u in us.list_users() if u.role.value == 'Certified Broker']
    buyer = next((u for u in us.list_users() if u.role.value == 'Buyer/Investor'), None)
    if len(brokers) >= 2:
        svc.allocate_broker('EG-CAI-01', brokers[0].user_id, brokers[0].full_name)
        svc.allocate_broker('EG-CAI-01', brokers[1].user_id, brokers[1].full_name)
        svc.allocate_broker('EG-SUZ-01', brokers[0].user_id, brokers[0].full_name)
        svc.record_broker_lead('EG-CAI-01', brokers[0].user_id)
        svc.record_broker_lead('EG-CAI-01', brokers[0].user_id)
        svc.record_broker_lead('EG-CAI-01', brokers[1].user_id)
        svc.record_broker_lead('EG-SUZ-01', brokers[0].user_id)
        if buyer:
            svc.close_deal(land_id='EG-SUZ-01', winning_broker_id=brokers[0].user_id, buyer_id=buyer.user_id, transaction_value_egp=462000000, broker_commission_pct=1.5)