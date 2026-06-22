"""
تهيئة Sentry لتتبع الأخطاء في الوقت الحقيقي
==============================================
Smart Land Management Copilot — Sentry Integration
====================================================
• تتبع الاستثناءات تلقائياً من كل خدمة FastAPI
• Performance Tracing — تتبع أوقات الطلبات والاستعلامات
• تصنيف الأخطاء حسب الخدمة والـ endpoint
• مصدر محلي للاختبار (Sentry Self-Hosted عبر Docker)
• Sentry Free Tier: 5,000 error/month مجاناً

الاستخدام:
    from monitoring.sentry_init import init_sentry
    init_sentry("land-service", release="1.0.0")

متغيرات البيئة:
  SENTRY_DSN           — رابط Sentry DSN (إذا فارغ = معطّل)
  SENTRY_ENVIRONMENT   — بيئة التشغيل (dev/staging/prod)
  SENTRY_TRACES_SAMPLE — نسبة أخذ عينات التتبع (0.0-1.0)
  SENTRY_PROFILES_SAMPLE — نسبة أخذ عينات الـ Profiling
"""

import logging
import os
from functools import wraps
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def init_sentry(
    service_name: str,
    release: str = "1.0.0",
    dsn: Optional[str] = None,
    environment: Optional[str] = None,
    traces_sample_rate: Optional[float] = None,
    profiles_sample_rate: Optional[float] = None,
    attach_log_handler: bool = True,
    before_send_callback=None,
) -> bool:
    """
    تهيئة Sentry لتتبع الأخطاء والأداء.

    Args:
        service_name: اسم الخدمة (يظهر في Sentry)
        release: رقم الإصدار
        dsn: رابط Sentry DSN (إن فارغ يبحث في SENTRY_DSN)
        environment: البيئة (إن فارغ يبحث في SENTRY_ENVIRONMENT)
        traces_sample_rate: نسبة أخذ عينات التتبع
        profiles_sample_rate: نسبة أخذ عينات الـ Profiling
        attach_log_handler: ربط سجلات Python بـ Sentry
        before_send_callback: دالة مخصصة لمعالجة الأحداث قبل الإرسال

    Returns:
        True إذا تم التهيئة بنجاح

    مثال Sentry DSN (مجاني):
        https://examplePublicKey@o0.ingest.sentry.io/0
    """
    dsn = dsn or os.environ.get("SENTRY_DSN", "")
    if not dsn:
        logger.info("Sentry معطّل — لم يتم توفير SENTRY_DSN")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.httpx import HttpxIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.requests import RequestsIntegration
    except ImportError:
        logger.warning(
            "sentry-sdk غير مثبت. ثبّته بـ: pip install sentry-sdk[fastapi]"
        )
        return False

    environment = environment or os.environ.get("SENTRY_ENVIRONMENT", "development")
    traces_rate = traces_sample_rate or float(
        os.environ.get("SENTRY_TRACES_SAMPLE", "0.1")  # 10% في التطوير
    )
    profiles_rate = profiles_sample_rate or float(
        os.environ.get("SENTRY_PROFILES_SAMPLE", "0.0")  # معطّل افتراضياً
    )

    def default_before_send(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        معالجة الأحداث قبل الإرسال — فلترة الضوضاء.
        """
        # تجاهل أخطاء 404 (ليست أخطاء حقيقية)
        if "exc_info" in hint:
            exc_type, exc_value, _ = hint["exc_info"]
            exc_name = getattr(exc_type, "__name__", str(exc_type))

            # تجاهل إلغاء الطلبات (client disconnect)
            if "CancelledError" in exc_name:
                return None

        # إضافة معلومات الخدمة
        event.setdefault("tags", {})["service"] = service_name

        # استدعاء callback مخصص إن وُجد
        if before_send_callback:
            event = before_send_callback(event, hint)
            if event is None:
                return None

        return event

    # ── دمج FastAPI ──
    fastapi_integration = FastApiIntegration(
        transaction_style="endpoint",
    )

    # ── دمج Logging ──
    log_level = logging.WARNING if environment == "production" else logging.INFO
    logging_integration = LoggingIntegration(
        level=log_level,        # مستوى إرسال السجلات لـ Sentry
        event_level=logging.ERROR,  # إنشاء event من ERROR فأعلى
    )

    integrations = [
        fastapi_integration,
        logging_integration,
        RequestsIntegration(),
    ]

    # إضافة Redis integration إن توفر
    try:
        integrations.append(RedisIntegration())
    except Exception:
        pass

    # إضافة Httpx integration إن توفر
    try:
        integrations.append(HttpxIntegration())
    except Exception:
        pass

    # ── التهيئة ──
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        sample_rate=1.0,  # إرسال 100% من الأخطاء
        traces_sample_rate=traces_rate,
        profiles_sample_rate=profiles_rate,
        integrations=integrations,
        before_send=default_before_send,
        # إعدادات إضافية
        send_default_pii=False,  # عدم إرسال بيانات شخصية
        attach_stacktrace=True,  # إرفاق stack trace دائماً
        max_breadcrumbs=50,
        max_request_body_size="medium",
    )

    # ── ربط سجلات Python ──
    if attach_log_handler:
        sentry_sdk.set_tag("service", service_name)

    logger.info(
        "تم تهيئة Sentry لـ %s — env=%s, traces=%.0f%%",
        service_name, environment, traces_rate * 100,
    )
    return True


def set_user_context(user_id: str, email: str = "", role: str = ""):
    """
    تعيين سياق المستخدم في Sentry.

    يظهر في كل خطأ ينتج عن هذا الطلب.

    الاستخدام:
        set_user_context("user-001", "investor@example.com", "admin")
    """
    try:
        import sentry_sdk
        sentry_sdk.set_user({
            "id": user_id,
            "email": email,
            "username": role,
        })
    except Exception:
        pass


def set_transaction_name(name: str):
    """
    تعيين اسم المعاملة الحالية.

    الاستخدام:
        set_transaction_name("matchmaking_query")
    """
    try:
        import sentry_sdk
        scope = sentry_sdk.get_current_scope()
        if scope:
            scope.set_transaction_name(name)
    except Exception:
        pass


def add_breadcrumb(
    message: str,
    category: str = "default",
    level: str = "info",
    data: Optional[Dict[str, Any]] = None,
):
    """
    إضافة breadcrumb لـ Sentry — خطوات تُظهر قبل الخطأ.

    الاستخدام:
        add_breadcrumb("بدأ البحث في الأراضي", category="search", data={"query": "صناعي"})
    """
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data or {},
        )
    except Exception:
        pass


def capture_exception(exc: Exception, extra: Optional[Dict[str, Any]] = None):
    """
    إرسال استثناء يدوياً لـ Sentry مع بيانات إضافية.

    الاستخدام:
        try:
            risky_operation()
        except Exception as e:
            capture_exception(e, extra={"land_id": "EG-CAI-01", "operation": "match"})
    """
    try:
        import sentry_sdk
        with sentry_sdk.configure_scope() as scope:
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, v)
        sentry_sdk.capture_exception(exc)
    except Exception:
        logger.debug("لم يتم إرسال الاستثناء لـ Sentry")


def capture_message(message: str, level: str = "info"):
    """
    إرسال رسالة يدوياً لـ Sentry.

    الاستخدام:
        capture_message("تم اكتشاف شذوذ في بيانات الأسعار", level="warning")
    """
    try:
        import sentry_sdk
        sentry_sdk.capture_message(message, level=level)
    except Exception:
        pass


def start_transaction(
    name: str,
    op: str = "http.server",
) -> Any:
    """
    بدء معاملة Sentry مخصصة لتتبع الأداء.

    الاستخدام:
        with start_transaction("full_matchmaking", op="business") as txn:
            # Step 1
            with txn.start_child(op="db.query", description="fetch_lands"):
                lands = get_all_lands()
            # Step 2
            with txn.start_child(op="compute", description="scoring"):
                results = compute_scores(lands)
    """
    try:
        import sentry_sdk
        return sentry_sdk.start_transaction(name=name, op=op)
    except Exception:
        # إرجاع context manager فارغ
        class _NoopTxn:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def start_child(self, **kw):
                return _NoopTxn()
        return _NoopTxn()


# ──────────────────────────────────────────────────────────────
# ديكور لتتبع الدوال
# ──────────────────────────────────────────────────────────────

def trace_function(operation_name: str = ""):
    """
    ديكور لتتبع وقت تنفيذ دالة وإرساله لـ Sentry.

    الاستخدام:
        @trace_function("fetch_lands")
        def get_all_lands():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                import sentry_sdk
            except ImportError:
                return func(*args, **kwargs)

            op_name = operation_name or func.__name__
            with sentry_sdk.start_span(op=op_name, description=func.__name__):
                return func(*args, **kwargs)
        return wrapper
    return decorator