"""
مخازن مشتركة ومساعدات — لمسارات account
=============================================
يستخدم النسخة المتزامنة في الذاكرة من microservices/account-service/
(المسارات تستدعي الدوال بدون await).
"""
import os
import sys
import logging
from typing import Optional, Dict, Any

from fastapi import Request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from infrastructure.persistence.account_store import (
    InvestorStore, LandownerStore,
    init_stores, transfer_ownership,
    investor_store_global, landowner_store_global, lands_catalog_global,
)

logger = logging.getLogger(__name__)

_investor_store_sync = None
_landowner_store_sync = None


def get_investor_store() -> InvestorStore:
    """إرجاع المخزن المتزامن للمستثمرين (يُهيّأ مرة واحدة)."""
    global _investor_store_sync
    if _investor_store_sync is None:
        _investor_store_sync, _ = init_stores()
    return _investor_store_sync


def get_landowner_store() -> LandownerStore:
    """إرجاع المخزن المتزامن لملاك الأراضي (يُهيّأ مرة واحدة)."""
    global _landowner_store_sync
    if _landowner_store_sync is None:
        _, _landowner_store_sync = init_stores()
    return _landowner_store_sync


def get_stores():
    """إرجاع كلا المخزنين (يضمن تهيئتهما معاً)."""
    global _investor_store_sync, _landowner_store_sync
    if _investor_store_sync is None:
        _investor_store_sync, _landowner_store_sync = init_stores()
    return _investor_store_sync, _landowner_store_sync


async def optional_user(request: Request) -> Optional[str]:
    """استخراج user_id من JWT header إن وُجد."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            import jwt
            JWT_SECRET = os.getenv("JWT_SECRET", "smartland-dev-secret-change-in-production")
            payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
            return payload.get("sub")
        except Exception:
            pass
    return None