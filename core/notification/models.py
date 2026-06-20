"""
Notification Models
====================
Data models for notifications and user preferences (non-ORM).
These are used by the NotificationService for the in-memory/API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Notification:
    """Notification data model."""
    id: str
    user_id: str
    type: str
    title: str
    body: str
    data: Optional[Dict[str, Any]] = None
    priority: int = 0
    is_read: bool = False
    dedup_key: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "data": self.data or {},
            "priority": self.priority,
            "is_read": self.is_read,
            "created_at": self.created_at,
        }


@dataclass
class UserNotificationPreference:
    """User notification preferences."""
    user_id: str
    channels: Dict[str, bool] = field(default_factory=lambda: {
        "push": True,
        "whatsapp": False,
        "email": True,
    })
    muted_event_types: List[str] = field(default_factory=list)
    fcm_device_token: Optional[str] = None
    email_address: Optional[str] = None
    whatsapp_number: Optional[str] = None

    def is_channel_enabled(self, channel: str) -> bool:
        return self.channels.get(channel, False)

    def is_event_muted(self, event_type: str) -> bool:
        return event_type in self.muted_event_types

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "channels": self.channels,
            "muted_event_types": self.muted_event_types,
            "fcm_device_token": self.fcm_device_token,
            "email_address": self.email_address,
            "whatsapp_number": self.whatsapp_number,
        }