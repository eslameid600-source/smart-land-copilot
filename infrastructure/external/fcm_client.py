"""
infrastructure.external.fcm_client
==================================
عميل Firebase Cloud Messaging — يعمل في وضع stub عند عدم تهيئة Firebase.

عند توفّر مسار ملف الـ service account JSON عبر FCM_SERVICE_ACCOUNT_PATH،
يتحول إلى وضع الإرسال الفعلي عبر firebase-admin.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# إعدادات FCM
# ──────────────────────────────────────────────

FCM_SERVICE_ACCOUNT_PATH = os.getenv("FCM_SERVICE_ACCOUNT_PATH", "")
FCM_DRY_RUN = os.getenv("FCM_DRY_RUN", "1") == "1"  # افتراضياً dry-run


def is_fcm_configured() -> bool:
    """هل FCM مهيّأ فعلياً؟"""
    return bool(FCM_SERVICE_ACCOUNT_PATH) and os.path.exists(FCM_SERVICE_ACCOUNT_PATH)


# ──────────────────────────────────────────────
# send_fcm_notification (async)
# ──────────────────────────────────────────────

async def send_fcm_notification(
    token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """إرسال إشعار push عبر FCM.

    Args:
        token: FCM device token
        title: عنوان الإشعار
        body: نص الإشعار
        data: حمولة بيانات إضافية (key-value)
        dry_run: لو True، لا يُرسل فعلياً (يُرجع نجاح وهمي)

    Returns:
        dict: {"success": bool, "dry_run": bool, "message_id": str | None, ...}
    """
    if dry_run is None:
        dry_run = FCM_DRY_RUN or not is_fcm_configured()

    if dry_run or not is_fcm_configured():
        # وضع stub / dry-run
        logger.info("[FCM STUB] token=%s title=%s", token[:12] + "..." if token else "", title)
        return {
            "success": True,
            "dry_run": True,
            "token": token,
            "title": title,
            "body": body,
            "data": data or {},
            "message_id": None,
        }

    # وضع الإرسال الفعلي عبر firebase-admin
    try:
        import firebase_admin  # noqa
        from firebase_admin import credentials, messaging

        # تهيئة التطبيق (مرة واحدة)
        if not firebase_admin._apps:
            cred = credentials.Certificate(FCM_SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred)

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )
        response = messaging.send(message)
        logger.info("[FCM] sent to %s: %s", token[:12] + "...", response)
        return {
            "success": True,
            "dry_run": False,
            "token": token,
            "title": title,
            "body": body,
            "data": data or {},
            "message_id": response,
        }
    except ImportError:
        logger.warning("firebase-admin غير مثبّت — العودة لوضع stub")
        return {
            "success": True,
            "dry_run": True,
            "token": token,
            "title": title,
            "body": body,
            "data": data or {},
            "message_id": None,
        }
    except Exception as e:
        logger.error("[FCM] فشل الإرسال: %s", e)
        return {
            "success": False,
            "dry_run": False,
            "token": token,
            "title": title,
            "body": body,
            "data": data or {},
            "error": str(e),
        }


__all__ = ["send_fcm_notification", "is_fcm_configured"]
