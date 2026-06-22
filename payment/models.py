"""payment.models — facade re-exporting PaymentTransaction from core.account.models."""

from core.account.models import PaymentTransaction  # noqa: F401

__all__ = ["PaymentTransaction"]
