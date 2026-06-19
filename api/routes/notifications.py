"""
Notification API Routes — نقاط نهاية الإشعارات
=================================================
FastAPI endpoints للإشعارات.

Endpoints:
    GET  /api/notifications              → جلب إشعارات المستخدم
    POST /api/notifications/read         → تحديد إشعار كمقروء
    POST /api/notifications/read-all     → تحديد الكل كمقروء
    PUT  /api/notifications/preferences  → تحديث تفضيلات المستخدم
    GET  /api/notifications/preferences  → جلب تفضيلات المستخدم
    GET  /api/notifications/unread-count → عدد غير المقروءة
    GET  /api/notifications/health       → فحص الصحة
"""

from __future__ import annotations

import os
import sys
import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.domain.entities import APIResponse, HealthResponse
from core.notification.service import NotificationService
from infrastructure.database import get_session

logger = logging.getLogger(__name__)

SERVICE_START = time.time()
SERVICE_VERSION = "1.0.0"

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ──────────────────────────────────────────────
# Helper: استخراج user_id من JWT
# ──────────────────────────────────────────────

async def _get_user_id(request: Request) -> str:
    """استخراج user_id من Bearer token."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    try:
        import jwt
        JWT_SECRET = os.getenv("JWT_SECRET", "smartland-dev-secret-change-in-production")
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token — no sub")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ══════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════

@router.get("/health", response_model=HealthResponse)
async def health():
    """فحص صحة خدمة الإشعارات."""
    redis_ok = False
    try:
        import redis
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD", ""),
            socket_timeout=2,
        )
        r.ping()
        redis_ok = True
    except Exception:
        pass

    return HealthResponse(
        service="notification-service",
        status="healthy" if redis_ok else "degraded",
        version=SERVICE_VERSION,
        uptime_seconds=round(time.time() - SERVICE_START, 1),
        dependencies={"redis": "connected" if redis_ok else "unavailable"},
    )


@router.get("/unread-count")
async def unread_count(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """عدد الإشعارات غير المقروءة."""
    user_id = await _get_user_id(request)
    svc = NotificationService(session)
    count = await svc.get_unread_count(user_id)
    return APIResponse(data={"unread_count": count})


@router.get("")
async def list_notifications(
    request: Request,
    only_unread: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """جلب إشعارات المستخدم — من الأحدث للأقدم."""
    user_id = await _get_user_id(request)
    svc = NotificationService(session)
    notifications, total = await svc.get_notifications(
        user_id=user_id,
        only_unread=only_unread,
        limit=limit,
        offset=offset,
    )
    return APIResponse(
        data=notifications,
        meta={"total": total, "limit": limit, "offset": offset},
    )


@router.post("/read")
async def mark_as_read(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    تحديد إشعار كمقروء.

    Body: {"notification_id": "..."}
    """
    user_id = await _get_user_id(request)
    body = await request.json()
    notification_id = body.get("notification_id", "")
    if not notification_id:
        raise HTTPException(status_code=400, detail="notification_id مطلوب")

    svc = NotificationService(session)
    updated = await svc.mark_as_read(notification_id, user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="الإشعار غير موجود أو لا يعود لك")

    return APIResponse(data={"marked": True, "notification_id": notification_id})


@router.post("/read-all")
async def mark_all_as_read(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """تحديد كل الإشعارات كمقروءة."""
    user_id = await _get_user_id(request)
    svc = NotificationService(session)
    count = await svc.mark_all_as_read(user_id)
    return APIResponse(data={"marked_count": count})


@router.get("/preferences")
async def get_preferences(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """جلب تفضيلات الإشعارات."""
    user_id = await _get_user_id(request)
    svc = NotificationService(session)
    prefs = await svc.get_preferences(user_id)
    if prefs is None:
        # إرجاع الافتراضي إذا لم تُعيّن بعد
        prefs = {
            "user_id": user_id,
            "channels": {"push": True, "whatsapp": False, "email": True},
            "muted_event_types": [],
        }
    return APIResponse(data=prefs)


@router.put("/preferences")
async def update_preferences(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    تحديث تفضيلات الإشعارات.

    Body:
        {
            "channels": {"push": true, "whatsapp": false, "email": true},
            "muted_event_types": ["survey_reminder"],
            "fcm_device_token": "...",
            "email_address": "user@example.com",
            "whatsapp_number": "+201000000000"
        }
    """
    user_id = await _get_user_id(request)
    body = await request.json()

    svc = NotificationService(session)
    result = await svc.update_preferences(
        user_id=user_id,
        channels=body.get("channels"),
        muted_event_types=body.get("muted_event_types"),
        fcm_device_token=body.get("fcm_device_token"),
        email_address=body.get("email_address"),
        whatsapp_number=body.get("whatsapp_number"),
    )
    return APIResponse(data=result, message="تم تحديث التفضيلات")


# ══════════════════════════════════════════════
# FastAPI App (قابل للتشغيل المستقل)
# ══════════════════════════════════════════════

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Smart Land — Notification Service",
    description="خدمة الإشعارات — Event-Driven مع Redis Pub/Sub",
    version=SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
async def _startup():
    """إنشاء جداول الإشعارات عند البدء."""
    from sqlalchemy import text
    from infrastructure.database import get_engine

    _CREATE_NOTIF_TABLES = """
    CREATE TABLE IF NOT EXISTS notifications (
        id              VARCHAR(36) PRIMARY KEY,
        user_id         VARCHAR(100) NOT NULL,
        type            VARCHAR(50)  NOT NULL,
        title           VARCHAR(300) NOT NULL,
        body            TEXT         NOT NULL,
        data            JSONB,
        is_read         BOOLEAN      NOT NULL DEFAULT FALSE,
        priority        INTEGER      NOT NULL DEFAULT 0,
        dedup_key       VARCHAR(255) UNIQUE,
        created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS user_notification_preferences (
        user_id             VARCHAR(100) PRIMARY KEY,
        channels            JSONB        NOT NULL DEFAULT '{"push":true,"whatsapp":false,"email":true}',
        muted_event_types   JSONB,
        fcm_device_token    VARCHAR(500),
        email_address       VARCHAR(255),
        whatsapp_number     VARCHAR(30),
        updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS ix_notif_user_id ON notifications(user_id);
    CREATE INDEX IF NOT EXISTS ix_notif_type ON notifications(type);
    CREATE INDEX IF NOT EXISTS ix_notif_is_read ON notifications(is_read);
    CREATE INDEX IF NOT EXISTS ix_notif_created ON notifications(created_at);
    CREATE INDEX IF NOT EXISTS ix_notif_user_unread ON notifications(user_id, is_read);
    CREATE INDEX IF NOT EXISTS ix_notif_user_created ON notifications(user_id, created_at);
    """
    try:
        eng = get_engine()
        async with eng.begin() as conn:
            await conn.execute(text(_CREATE_NOTIF_TABLES))
        logger.info("Notification tables created/verified")
    except Exception as e:
        logger.error(f"Failed to create notification tables: {e}")