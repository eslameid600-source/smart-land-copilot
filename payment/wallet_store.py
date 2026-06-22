"""payment.wallet_store — facade re-exporting WalletStore from core.account.wallet_store."""

from core.account.wallet_store import WalletOperationsMixin as WalletStore  # noqa: F401

__all__ = ["WalletStore"]
