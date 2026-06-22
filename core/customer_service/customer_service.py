"""
Smart Land Management Copilot — Customer Service System
=========================================================
Support ticket management, auto-escalation, and satisfaction tracking.
"""
import uuid
from typing import Dict, List, Optional

from models.models.ticket import SupportTicket, TicketPriority, TicketStatus

from config.settings import get_settings


class CustomerServiceSystem:
    """
    Manages support tickets, auto-escalation for complex queries,
    and satisfaction survey tracking.
    """

    def __init__(self):
        self._tickets: Dict[str, SupportTicket] = {}
        self._chat_counts: Dict[str, int] = {}
        self._settings = get_settings()

    def create_ticket(self, query: str, session_id: str='default', priority: Optional[str]=None) -> SupportTicket:
        """Create a new support ticket from a user query."""
        ticket_id = f'TK-{uuid.uuid4().hex[:8].upper()}'
        if priority is None:
            priority = self._classify_priority(query)
        category = self._classify_category(query)
        ticket = SupportTicket(ticket_id=ticket_id, user_query=query, category=category, priority=TicketPriority(priority))
        if self._should_escalate(query):
            ticket.escalate('Query contains escalation-trigger keywords')
        self._tickets[ticket_id] = ticket
        self._chat_counts[session_id] = self._chat_counts.get(session_id, 0) + 1
        return ticket

    def get_ticket(self, ticket_id: str) -> Optional[SupportTicket]:
        return self._tickets.get(ticket_id)

    def get_all_tickets(self) -> List[SupportTicket]:
        return list(self._tickets.values())

    def get_open_tickets(self) -> List[SupportTicket]:
        return [t for t in self._tickets.values() if t.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)]

    def get_escalated_tickets(self) -> List[SupportTicket]:
        return [t for t in self._tickets.values() if t.status == TicketStatus.ESCALATED]

    def resolve_ticket(self, ticket_id: str, resolution: str) -> bool:
        ticket = self._tickets.get(ticket_id)
        if ticket:
            ticket.resolve(resolution)
            return True
        return False

    def should_show_satisfaction_survey(self, session_id: str) -> bool:
        """Check if the user has chatted enough to trigger a satisfaction survey."""
        threshold = self._settings.satisfaction_survey_after_n_chats
        return self._chat_counts.get(session_id, 0) >= threshold

    def record_satisfaction(self, ticket_id: str, score: int) -> bool:
        ticket = self._tickets.get(ticket_id)
        if ticket and 1 <= score <= 5:
            ticket.satisfaction_score = score
            ticket.close()
            return True
        return False

    def get_satisfaction_stats(self) -> Dict:
        """Get aggregate satisfaction metrics."""
        scored = [t for t in self._tickets.values() if t.satisfaction_score is not None]
        if not scored:
            return {'avg_score': 0, 'total_rated': 0, 'distribution': {}}
        scores = [t.satisfaction_score for t in scored]
        distribution = {}
        for s in range(1, 6):
            distribution[str(s)] = scores.count(s)
        return {'avg_score': round(sum(scores) / len(scores), 2), 'total_rated': len(scored), 'distribution': distribution}

    def get_dashboard_metrics(self) -> Dict:
        """Get customer service KPIs for the PM dashboard."""
        all_t = list(self._tickets.values())
        return {'total_tickets': len(all_t), 'open_tickets': len([t for t in all_t if t.status == TicketStatus.OPEN]), 'escalated_tickets': len([t for t in all_t if t.status == TicketStatus.ESCALATED]), 'resolved_tickets': len([t for t in all_t if t.status == TicketStatus.RESOLVED]), 'avg_satisfaction': self.get_satisfaction_stats()['avg_score'], 'auto_escalation_rate': len([t for t in all_t if t.auto_escalated]) / max(len(all_t), 1) * 100}

    def _should_escalate(self, query: str) -> bool:
        """Check if query contains keywords that trigger auto-escalation."""
        query_lower = query.lower()
        return any((kw.lower() in query_lower for kw in self._settings.auto_escalate_keywords))

    @staticmethod
    def _classify_priority(query: str) -> str:
        """Auto-classify ticket priority based on query content."""
        query_lower = query.lower()
        critical_kw = ['urgent', 'emergency', 'immediately', 'asap', 'complaint', 'problem', 'wrong']
        high_kw = ['legal', 'lawyer', 'contract', 'refund', 'dispute', 'cancel']
        medium_kw = ['how', 'what', 'compare', 'recommend', 'analysis']
        if any((kw in query_lower for kw in critical_kw)):
            return 'Critical'
        elif any((kw in query_lower for kw in high_kw)):
            return 'High'
        elif any((kw in query_lower for kw in medium_kw)):
            return 'Medium'
        return 'Low'

    @staticmethod
    def _classify_category(query: str) -> str:
        """Auto-classify the ticket category."""
        query_lower = query.lower()
        categories = {'Financial': ['price', 'cost', 'tax', 'roi', 'irr', 'budget', 'payment', 'fee'], 'Legal': ['law', 'legal', 'permit', 'license', 'contract', 'regulation', 'nuca', 'gafi'], 'Technical': ['map', 'data', 'api', 'error', 'bug', 'system', 'loading'], 'Market Analysis': ['trend', 'predict', 'forecast', 'market', 'appreciation'], 'Land Info': ['soil', 'geological', 'infrastructure', 'utility', 'water', 'electricity'], 'General Inquiry': []}
        for cat, keywords in categories.items():
            if any((kw in query_lower for kw in keywords)):
                return cat
        return 'General Inquiry'