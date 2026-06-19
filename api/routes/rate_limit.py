# -*- coding: utf-8 -*-
"""
api/middleware/rate_limit.py
============================

إعداد Rate Limiting لتطبيق FastAPI باستخدام slowapi.

الاستخدام في api/routes/main.py:

    from fastapi import FastAPI
    from api.middleware.rate_limit import init_rate_limiting, limiter

    app = FastAPI()
    init_rate_limiting(app)        # يربط الـ limiter ومعالج تجاوز الحد

    @app.get("/investors/me")
    @limiter.limit("100/minute")   # المسارات الحسّاسة فقط
    async def me(request: Request):
        ...

ملاحظات مهمة:
- لا تضع limiter على /health أو نقاط الفحص — وإلا ستفشل اختبارات التحميل.
- المفتاح الافتراضي هو عنوان IP للعميل (get_remote_address).
- يمكن استبدال التخزين الافتراضي (الذاكرة) بـ Redis عند التشغيل بعدة نسخ:
      Limiter(key_func=..., storage_uri="redis://localhost:6379")
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

# الحدّ الافتراضي العام (قابل للتجاوز عبر متغيّر بيئة)
DEFAULT_LIMIT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")

# تخزين الحالة: ذاكرة محليّاً، أو Redis عند توفّره (للتشغيل متعدّد النسخ)
STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")

# الـ Limiter العام — يُستورد في ملفات المسارات لاستخدام @limiter.limit(...)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[DEFAULT_LIMIT],
    storage_uri=STORAGE_URI,
    headers_enabled=True,  # يضيف ترويسات X-RateLimit-* للردود
)


def init_rate_limiting(app: FastAPI) -> None:
    """يربط الـ limiter بتطبيق FastAPI ويسجّل معالج تجاوز الحد (يرجع 429)."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
