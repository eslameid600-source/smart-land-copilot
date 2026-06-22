"""payment.transaction_service — facade re-exporting TransactionService.

The actual TransactionService class is defined in
core.account.transaction_service. We re-export it here so that
imports of the form `from payment.transaction_service import TransactionService`
keep working.
"""

from core.account.transaction_service import TransactionService  # noqa: F401

__all__ = ["TransactionService"]
