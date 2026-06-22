"""
مخازن مشتركة ومساعدات — لمسارات account
=============================================
يستخدم النسخة المتزامنة في الذاكرة من microservices/account-service/
(المسارات تستدعي الدوال بدون await).
"""
import logging
import os
import sys
from typing import Optional

from fastapi import Request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.routes.account_store import (
    InvestorStore,
    LandownerStore,
    init_stores,
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
    """استخراج user_id من JWT header إن وُجد.

    الأمان: JWT_SECRET يجب أن يُضبط عبر متغير البيئة. لو لم يُضبط،
    تُرجع None بصمت (هذه دالة optional — لا ترفع استثناء).
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        JWT_SECRET = os.getenv("JWT_SECRET")
        if not JWT_SECRET:
            logger.warning("JWT_SECRET env var not set — optional_user returns None")
            return None
        try:
            import jwt
            payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
            return payload.get("sub")
        except Exception:
            pass
    return None