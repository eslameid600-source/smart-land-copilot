"""
core.notification.models
========================
نماذج بيانات الإشعارات (dataclasses — يمكن تحويلها لـ SQLAlchemy لاحقاً).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
# Notification
# ──────────────────────────────────────────────

@dataclass
class Notification:
    """سجل إشعار واحد مُوجَّه لمستخدم."""
    id: str
    user_id: str
    type: str                                           # key من EVENT_REGISTRY
    title: str
    body: str
    data: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    is_read: bool = False
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "data": self.data,
            "priority": self.priority,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────
# UserNotificationPreference
# ──────────────────────────────────────────────

@dataclass
class UserNotificationPreference:
    """تفضيلات الإشعارات لمستخدم: قنوات مفعّلة + أنواع مكتومة + بيانات تواصل."""
    user_id: str
    channels: Dict[str, bool] = field(default_factory=lambda: {
        "push": True, "whatsapp": True, "email": True, "in_app": True,
    })
    muted_event_types: List[str] = field(default_factory=list)
    fcm_device_token: Optional[str] = None
    email_address: Optional[str] = None
    phone_number: Optional[str] = None

    def is_channel_enabled(self, channel: str) -> bool:
        """هل القناة مفعّلة لهذا المستخدم؟"""
        return self.channels.get(channel, False)

    def is_event_muted(self, event_type: str) -> bool:
        """هل هذا النوع من الأحداث مكتوم؟"""
        return event_type in self.muted_event_types

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "channels": dict(self.channels),
            "muted_event_types": list(self.muted_event_types),
            "fcm_device_token": self.fcm_device_token,
            "email_address": self.email_address,
            "phone_number": self.phone_number,
        }


__all__ = ["Notification", "UserNotificationPreference"]
