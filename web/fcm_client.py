"""
Firebase Cloud Messaging — FCM Client
========================================
إرسال Push Notifications للأجهزة الجوالة عبر FCM.

التركيب:
    pip install firebase-admin

التهيئة:
    export FCM_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
    أو في Docker: volume mount الملف إلى /app/fcm-service-account.json
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── مسار ملف حساب الخدمة ──
FCM_CREDENTIALS_PATH = os.getenv(
    "FCM_SERVICE_ACCOUNT_JSON",
    "/app/fcm-service-account.json",
)

_fcm_app = None


def _get_fcm_app():
    """
    تهيئة Firebase App مرة واحدة (Singleton).
    يُرجع None إذا لم يتوفر ملف الحساب.
    """
    global _fcm_app
    if _fcm_app is not None:
        return _fcm_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _fcm_app = list(firebase_admin._apps.values())[0]
            return _fcm_app

        if not os.path.isfile(FCM_CREDENTIALS_PATH):
            logger.warning(
                f"FCM credentials not found at {FCM_CREDENTIALS_PATH} "
                "— push notifications disabled"
            )
            return None

        cred = credentials.Certificate(FCM_CREDENTIALS_PATH)
        _fcm_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin initialized for FCM")
        return _fcm_app

    except ImportError:
        logger.warning("firebase-admin not installed — push notifications disabled")
        return None
    except Exception as e:
        logger.error(f"FCM initialization failed: {e}")
        return None


async def send_fcm_notification(
    device_token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    إرسال Push Notification عبر FCM.

    المعاملات:
        device_token: رمز جهاز FCM
        title:        عنوان الإشعار
        body:         نص الإشعار
        data:         بيانات إضافية (مفتاح/قيمة)
        dry_run:      True = لا يُرسل فعلياً (للاختبار)

    المخرجات:
        {"success": bool, "message_id": str|None, "error": str|None}
    """
    app = _get_fcm_app()
    if app is None:
        logger.info(f"[FCM-Stub] send to {device_token[:20]}...: {title}")
        return {
            "success": True,
            "message_id": f"stub-fcm-{id(device_token)}",
            "error": None,
            "dry_run": True,
        }

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data={
                k: str(v) for k, v in (data or {}).items()
            } if data else None,
            token=device_token,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    sound="default",
                    channel_id="smartland_notifications",
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound="default",
                        badge=1,
                    ),
                ),
            ),
        )

        response = messaging.send(message, dry_run=dry_run)
        logger.info(f"FCM sent: {response}")
        return {
            "success": True,
            "message_id": response,
            "error": None,
        }

    except messaging.UnregisteredError:
        logger.warning(f"FCM: invalid token {device_token[:20]}...")
        return {"success": False, "message_id": None, "error": "unregistered"}
    except messaging.QuotaExceededError:
        logger.error("FCM: quota exceeded")
        return {"success": False, "message_id": None, "error": "quota_exceeded"}
    except Exception as e:
        logger.error(f"FCM send error: {e}")
        return {"success": False, "message_id": None, "error": str(e)[:100]}


def send_fcm_multicast(
    tokens: list[str],
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    إرسال Push Notification لعدة أجهزة دفعة واحدة.

    المخرجات:
        {"success_count": int, "failure_count": int, "results": [...]}
    """
    app = _get_fcm_app()
    if app is None:
        return {
            "success_count": len(tokens),
            "failure_count": 0,
            "results": [{"token": t, "success": True} for t in tokens],
        }

    try:
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()} if data else None,
            tokens=tokens,
        )

        response = messaging.send_each_for_multicast(message)

        results = []
        for i, (token, resp) in enumerate(zip(tokens, response.responses)):
            results.append({
                "token": token[:20] + "...",
                "success": resp.success,
                "error": str(resp.exception) if resp.exception else None,
            })

        logger.info(
            f"FCM multicast: {response.success_count} ok, "
            f"{len(tokens) - response.success_count} failed"
        )
        return {
            "success_count": response.success_count,
            "failure_count": len(tokens) - response.success_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"FCM multicast error: {e}")
        return {
            "success_count": 0,
            "failure_count": len(tokens),
            "results": [{"token": t, "success": False, "error": str(e)[:80]} for t in tokens],
        }