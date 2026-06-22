"""services.customer_service — facade re-exporting WhatsAppService + CustomerServiceSystem.

Provides:
    - WhatsAppService, WhatsAppMessage, WebhookEvent, etc. (from api.routes.whatsapp_service)
    - CustomerServiceSystem: aggregate class that ties WhatsApp + email + notifications
    - send_whatsapp_message: convenience function
"""

from typing import Optional

from api.routes.whatsapp_service import (  # noqa: F401
    WhatsAppService,
    WhatsAppMessage,
    WebhookEvent,
    TemplateManager,
    MessageDirection,
    MessageStatus,
    Provider,
)


class CustomerServiceSystem:
    """Aggregate customer-service facade.

    Wraps WhatsAppService + notification + email channels into a single
    object that the UI can call.
    """

    def __init__(self):
        self.whatsapp = WhatsAppService()
        self._notifications_sent: int = 0

    def send_whatsapp(self, to: str, body: str, **kwargs) -> Optional[WhatsAppMessage]:
        try:
            return self.whatsapp.send_message(to=to, body=body, **kwargs)
        except Exception:
            return None

    def send_email(self, to: str, subject: str, body: str) -> bool:
        try:
            from infrastructure.external.email_service import send_email
            return send_email(to, subject, body)
        except Exception:
            return False

    def send_push(self, user_id: str, title: str, body: str) -> bool:
        try:
            from infrastructure.external.fcm_client import send_fcm_notification
            return send_fcm_notification(token="", title=title, body=body)
        except Exception:
            return False

    @property
    def notifications_sent(self) -> int:
        return self._notifications_sent


def send_whatsapp_message(to: str, body: str, **kwargs):
    """Convenience helper — send a WhatsApp message via WhatsAppService."""
    try:
        return WhatsAppService().send_message(to=to, body=body, **kwargs)
    except Exception:
        return None


__all__ = [
    "WhatsAppService",
    "WhatsAppMessage",
    "WebhookEvent",
    "TemplateManager",
    "MessageDirection",
    "MessageStatus",
    "Provider",
    "CustomerServiceSystem",
    "send_whatsapp_message",
]
