"""infrastructure.external.customer_service — facade re-exporting from api.routes.whatsapp_service."""

from api.routes.whatsapp_service import WhatsAppService  # noqa: F401

__all__ = ["WhatsAppService"]
