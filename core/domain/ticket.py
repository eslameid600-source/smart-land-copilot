"""
Smart Land Management Copilot — Support Ticket Model
======================================================
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TicketStatus(str, Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    ESCALATED = "Escalated to Human Agent"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class TicketPriority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class SupportTicket(BaseModel):
    """Customer support ticket for complex queries."""
    ticket_id: str
    user_query: str
    category: str = Field(default="General Inquiry")
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM)
    status: TicketStatus = Field(default=TicketStatus.OPEN)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    assigned_to: Optional[str] = Field(default=None, description="Agent name or 'AI Copilot'")
    conversation_history: List[dict] = Field(default_factory=list)
    resolution: Optional[str] = None
    satisfaction_score: Optional[int] = Field(default=None, ge=1, le=5)
    auto_escalated: bool = Field(default=False, description="Auto-flagged for human agent")

    def escalate(self, reason: str = "Complex query requires human review") -> None:
        self.status = TicketStatus.ESCALATED
        self.auto_escalated = True
        self.conversation_history.append({
            "role": "system",
            "content": f"TICKET ESCALATED: {reason}",
            "timestamp": datetime.now().isoformat(),
        })

    def resolve(self, resolution: str) -> None:
        self.status = TicketStatus.RESOLVED
        self.resolution = resolution
        self.updated_at = datetime.now()

    def close(self) -> None:
        self.status = TicketStatus.CLOSED
        self.updated_at = datetime.now()