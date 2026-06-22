"""
Notification Worker — Celery Worker
=====================================
يعالج أحداث الإشعارات من Redis Pub/Sub و Redis Stream
ويُرسلها عبر القنوات المفعلة (Push, WhatsApp, Email).

التشغيل:
    celery -A notification_worker worker --loglevel=info --concurrency=4

أو بدون Celery (mode مباشر مع Redis listener):
    python notification_worker.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Optional

# ── إعداد المسارات ──
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("notification_worker")


# ══════════════════════════════════════════════
# 1. إعداد Redis
# ══════════════════════════════════════════════

def _get_redis() -> Any:
    """إرجاع عميل Redis (sync لـ Celery / async للوضع المباشر)."""
    import redis as redis_lib
    return redis_lib.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD", ""),
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5,
    )


def _get_async_redis():
    """إرجاع عميل Redis غير متزامن."""
    import redis.asyncio as aioredis
    return aioredis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD", ""),
        decode_responses=True,
    )


# ══════════════════════════════════════════════
# 2. التوصيل بقنوات الإرسال
# ══════════════════════════════════════════════

async def _send_via_push(
    user_id: str, title: str, body: str, data: dict
) -> dict:
    """إرسال Push عبر FCM."""
    # جلب FCM token من تفضيلات المستخدم
    token = await _get_user_fcm_token(user_id)
    if not token:
        logger.info(f"No FCM token for {user_id}")
        return {"channel": "push", "status": "skipped", "reason": "no_token"}

    from infrastructure.external.fcm_client import send_fcm_notification
    result = await send_fcm_notification(token, title, body, data)
    return {"channel": "push", **result}


async def _send_via_whatsapp(
    user_id: str, title: str, body: str, data: dict
) -> dict:
    """إرسال عبر WhatsApp."""
    phone = await _get_user_whatsapp_number(user_id)
    if not phone:
        return {"channel": "whatsapp", "status": "skipped", "reason": "no_number"}

    from infrastructure.external.customer_service.whatsapp_service import \
        WhatsAppService
    TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER", "")

    svc = WhatsAppService(TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM)

    # تحديد اسم القالب من نوع الحدث
    event_type = data.get("event_type", "")
    template_name = f"notif_{event_type}"

    result = svc.send_template(
        to_number=phone,
        template_name=template_name,
        params=[title, body[:100]],
    )
    return {"channel": "whatsapp", "status": "sent", "sid": result.get("sid")}


async def _send_via_email(
    user_id: str, title: str, body: str, data: dict
) -> dict:
    """إرسال عبر البريد الإلكتروني."""
    email = await _get_user_email(user_id)
    if not email:
        return {"channel": "email", "status": "skipped", "reason": "no_email"}

    from infrastructure.external.email_service import (
        build_notification_email_html, send_email)
    event_type = data.get("event_type", "")
    html = build_notification_email_html(title, body, event_type)

    result = await send_email(
        subject=f"Smart Land — {title}",
        body=body,
        recipient=email,
        html_body=html,
    )
    return {"channel": "email", **result}


# ──────────────────────────────────────────────
# جلب بيانات الاتصال من PostgreSQL
# ──────────────────────────────────────────────

async def _get_user_preferences_sync(user_id: str) -> Optional[dict]:
    """جلب تفضيلات المستخدم (sync — للاستخدام من Celery)."""
    try:
        from sqlalchemy import create_engine, text
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url:
            host = os.getenv("DATABASE_HOST", "localhost")
            port = os.getenv("DATABASE_PORT", "5432")
            name = os.getenv("DATABASE_NAME", "smartland")
            user = os.getenv("DATABASE_USER", "smartland")
            pw = os.getenv("DATABASE_PASSWORD", "smartland123")
            db_url = f"postgresql://{user}:{pw}@{host}:{port}/{name}"

        # استبدال asyncpg بـ psycopg2 للاتصال المتزامن
        db_url = db_url.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")

        engine = create_engine(db_url)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT channels, muted_event_types, fcm_device_token, "
                    "email_address, whatsapp_number "
                    "FROM user_notification_preferences WHERE user_id = :uid"
                ),
                {"uid": user_id},
            ).first()

            if row:
                return {
                    "channels": row[0],
                    "muted_event_types": row[1] or [],
                    "fcm_device_token": row[2],
                    "email_address": row[3],
                    "whatsapp_number": row[4],
                }
    except Exception as e:
        logger.error(f"Failed to fetch preferences for {user_id}: {e}")
    return None


async def _get_user_fcm_token(user_id: str) -> Optional[str]:
    prefs = await _get_user_preferences_sync(user_id)
    return prefs["fcm_device_token"] if prefs else None


async def _get_user_email(user_id: str) -> Optional[str]:
    prefs = await _get_user_preferences_sync(user_id)
    return prefs["email_address"] if prefs else None


async def _get_user_whatsapp_number(user_id: str) -> Optional[str]:
    prefs = await _get_user_preferences_sync(user_id)
    return prefs["whatsapp_number"] if prefs else None


# ══════════════════════════════════════════════
# 3. معالجة الحدث — Core Logic
# ══════════════════════════════════════════════

async def _process_notification(message: dict) -> list[dict]:
    """
    معالجة إشعار واحد — يُرسل عبر القنوات المفعلة.

    المعاملات:
        message: الحمولة من Redis (تحتوي notification_id, user_id, type, title, body, data)

    المخرجات:
        قائمة نتائج كل قناة
    """
    user_id = message["user_id"]
    event_type = message.get("event_type", "")
    title = message["title"]
    body = message["body"]
    data = message.get("data", {})

    logger.info(f"Processing: {event_type} → {user_id}")

    # جلب تفضيلات المستخدم
    prefs = await _get_user_preferences_sync(user_id)
    if prefs is None:
        # لا تفضيلات = إرسال In-App فقط (مخزّن مسبقاً)
        logger.info(f"No preferences for {user_id} — In-App only")
        return [{"channel": "in_app", "status": "stored"}]

    channels = prefs.get("channels", {})
    muted = prefs.get("muted_event_types", [])

    # التحقق من الكتم
    if event_type in muted:
        logger.info(f"Event {event_type} muted for {user_id}")
        return [{"channel": "in_app", "status": "stored", "muted": True}]

    results = []

    # Push
    if channels.get("push"):
        try:
            r = await _send_via_push(user_id, title, body, data)
            results.append(r)
        except Exception as e:
            logger.error(f"Push failed for {user_id}: {e}")
            results.append({"channel": "push", "status": "error", "error": str(e)[:80]})

    # WhatsApp
    if channels.get("whatsapp"):
        try:
            r = await _send_via_whatsapp(user_id, title, body, data)
            results.append(r)
        except Exception as e:
            logger.error(f"WhatsApp failed for {user_id}: {e}")
            results.append({"channel": "whatsapp", "status": "error", "error": str(e)[:80]})

    # Email
    if channels.get("email"):
        try:
            r = await _send_via_email(user_id, title, body, data)
            results.append(r)
        except Exception as e:
            logger.error(f"Email failed for {user_id}: {e}")
            results.append({"channel": "email", "status": "error", "error": str(e)[:80]})

    logger.info(
        f"Delivered to {len(results)} channels for {user_id}: "
        f"{[r['channel'] for r in results]}"
    )
    return results


# ══════════════════════════════════════════════
# 4. Redis Listener — Pub/Sub + Stream
# ══════════════════════════════════════════════

async def run_listener():
    """
    حلقة الاستماع الرئيسية — تستمع لـ Redis Pub/Sub و Redis Stream.
    تُستخدم للتشغيل المباشر بدون Celery.
    """
    import asyncio

    r = _get_async_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("smartland:notifications")

    logger.info("Notification worker started — listening on Redis Pub/Sub")

    # أيضاً استمع للـ Stream (للمهام المفقودة)
    stream_tasks = set()

    async def process_stream():
        """قراءة الرسائل المفقودة من Redis Stream."""
        try:
            last_id = "0-0"
            while True:
                results = await r.xread(
                    {"smartland:notification_stream": last_id},
                    count=10, block=2000,
                )
                if not results:
                    await asyncio.sleep(1)
                    continue

                for stream_name, messages in results:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        try:
                            # تحويل الحقول من JSON
                            message = {
                                k: json.loads(v) if isinstance(v, str) and v.startswith("{") else v
                                for k, v in fields.items()
                            }
                            await _process_notification(message)
                        except Exception as e:
                            logger.error(f"Stream processing error: {e}")

                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Stream listener error: {e}")

    # تشغيل stream listener في خلفية
    stream_task = asyncio.create_task(process_stream())
    stream_tasks.add(stream_task)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                payload = json.loads(message["data"])
                await _process_notification(payload)
            except json.JSONDecodeError:
                logger.error("Invalid JSON in Pub/Sub message")
            except Exception as e:
                logger.error(f"Pub/Sub processing error: {e}")

    except asyncio.CancelledError:
        logger.info("Worker shutting down...")
    finally:
        await pubsub.unsubscribe()
        await r.aclose()
        for t in stream_tasks:
            t.cancel()


# ══════════════════════════════════════════════
# 5. Celery Integration (اختياري)
# ══════════════════════════════════════════════

try:
    from celery import Celery

    # تهيئة Celery (يُستخدم فقط إذا توفر Redis)
    _celery_app = Celery(
        "smartland_notifications",
        broker=os.getenv("CELERY_BROKER", "redis://localhost:6379/0"),
        backend=os.getenv("CELERY_BACKEND", "redis://localhost:6379/1"),
    )
    _celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Africa/Cairo",
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )

    @_celery_app.task(
        name="send_notification",
        max_retries=3,
        default_retry_delay=5,
        retry_backoff=True,
    )
    def send_notification_task(user_id: str, event_type: str, payload: dict):
        """
        مهمة Celery لإرسال إشعار.

        يُستدعى من:
            send_notification_task.delay(user_id, "auction_outbid", {...})
        """
        import asyncio

        message = {
            "user_id": user_id,
            "event_type": event_type,
            "title": payload.get("title", event_type),
            "body": payload.get("body", ""),
            "data": payload,
        }

        # تشغيل معالجة الحدث في event loop جديد
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_process_notification(message))
            return {"status": "sent", "channels": len(result)}
        except Exception as exc:
            logger.error(f"Celery task failed: {exc}")
            raise send_notification_task.retry(exc=exc)

    logger.info("Celery tasks registered")

except ImportError:
    logger.info("Celery not installed — using direct Redis listener mode")
    _celery_app = None


# ══════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio
    logger.info("Starting notification worker (direct mode)...")
    asyncio.run(run_listener())