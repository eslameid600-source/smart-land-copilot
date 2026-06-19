"""
وسيط المقاييس لـ FastAPI — Prometheus Metrics Middleware
==========================================================
Smart Land Management Copilot — Metrics Collection Middleware
=============================================================
• Request Rate (طلبات/ثانية) لكل endpoint + method
• Latency P50 / P95 / P99 عبر Histogram بأدوات تجميع ذكية
• Error Rate (4xx / 5xx) لكل endpoint
• In-Flight Requests (طلبات قيد التنفيذ حالياً)
• Response Size (حجم الاستجابة بالبايت)
• Business Metrics — أوقات LLM، نجاح المطابقة، تسجيل المستخدمين
• يتكامل تلقائياً مع أي تطبيق FastAPI عبر app.include_middleware()

الاستخدام:
    from monitoring.metrics_middleware import setup_metrics
    setup_metrics(app, service_name="land-service")

مقاييس Prometheus المُنتجة:
    http_requests_total{method, endpoint, status}
    http_request_duration_seconds{method, endpoint} — مع P50/P95/P99
    http_requests_in_flight{method, endpoint}
    http_response_size_bytes{method, endpoint}
    llm_request_duration_seconds{provider, mode}
    business_operations_total{operation, status}
    app_info{service, version}
"""

import os
import time
import logging
from typing import Optional, Dict, Any, Callable, List
from functools import wraps

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 1. استيراد prometheus_client (اختياري)
# ──────────────────────────────────────────────────────────────

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        Info,
        generate_latest,
        CONTENT_TYPE_LATEST,
        REGISTRY,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning(
        "prometheus_client غير مثبت. "
        "ثبّته بـ: pip install prometheus-client"
    )


# ──────────────────────────────────────────────────────────────
# 2. تعريف المقاييس
# ──────────────────────────────────────────────────────────────

# أدوات تجميع زمن الاستجابة — مصممة لـ FastAPI microservices
# 1ms إلى 60 ثانية مع تركيز على النطاق 10ms-5s
LATENCY_BUCKETS = [
    0.001,   # 1ms
    0.005,   # 5ms
    0.01,    # 10ms
    0.025,   # 25ms
    0.05,    # 50ms
    0.1,     # 100ms
    0.25,    # 250ms
    0.5,     # 500ms
    1.0,     # 1s
    2.5,     # 2.5s
    5.0,     # 5s
    10.0,    # 10s
    30.0,    # 30s
    60.0,    # 60s
    float("inf"),
]

if PROMETHEUS_AVAILABLE:
    # ── مقاييس HTTP العامة ──
    REQUEST_COUNT = Counter(
        "http_requests_total",
        "إجمالي طلبات HTTP",
        ["service", "method", "endpoint", "status_code"],
    )

    REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "زمن استجابة HTTP بالثواني",
        ["service", "method", "endpoint"],
        buckets=LATENCY_BUCKETS,
    )

    REQUESTS_IN_FLIGHT = Gauge(
        "http_requests_in_flight",
        "طلبات HTTP قيد التنفيذ حالياً",
        ["service", "method", "endpoint"],
    )

    RESPONSE_SIZE = Histogram(
        "http_response_size_bytes",
        "حجم استجابة HTTP بالبايت",
        ["service", "method", "endpoint"],
        buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000, float("inf")],
    )

    # ── مقاييس الأخطاء المفصّلة ──
    ERROR_COUNT = Counter(
        "http_errors_total",
        "إجمالي أخطاء HTTP",
        ["service", "method", "endpoint", "error_class", "status_code"],
    )

    # ── مقاييس الأعمال (Business Metrics) ──
    BUSINESS_OPS = Counter(
        "business_operations_total",
        "عمليات الأعمال",
        ["service", "operation", "status"],  # status: success/failure
    )

    LLM_DURATION = Histogram(
        "llm_request_duration_seconds",
        "زمن استجابة LLM بالثواني",
        ["service", "provider", "mode"],  # provider: glm/ollama/mock, mode: chat/match/advisory
        buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, float("inf")],
    )

    LLM_TOKENS = Counter(
        "llm_tokens_total",
        "إجمالي رموز LLM المستخدمة",
        ["service", "provider", "direction"],  # direction: prompt/completion
    )

    # ── مقاييس النظام ──
    APP_INFO = Info(
        "app_info",
        "معلومات التطبيق",
    )

    AUTH_OPS = Counter(
        "auth_operations_total",
        "عمليات المصادقة",
        ["service", "operation", "status"],
    )

    # ── مقاييس قاعدة البيانات / الذاكرة ──
    DB_QUERY_DURATION = Histogram(
        "db_query_duration_seconds",
        "زمن استعلامات قاعدة البيانات",
        ["service", "operation"],
        buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, float("inf")],
    )

    CACHE_OPERATIONS = Counter(
        "cache_operations_total",
        "عمليات الذاكرة المؤقتة",
        ["service", "operation", "hit"],  # hit: true/false
    )


# ──────────────────────────────────────────────────────────────
# 3. وسيط المقاييس (ASGI Middleware)
# ──────────────────────────────────────────────────────────────

class MetricsMiddleware:
    """
    وسيط ASGI لجمع مقاييس HTTP لكل طلب.

    يجمع تلقائياً:
    • عدد الطلبات (request count)
    • زمن الاستجابة (latency histogram → P50/P95/P99)
    • الأخطاء (4xx, 5xx)
    • الطلبات قيد التنفيذ (in-flight gauge)
    • حجم الاستجابة
    """

    # نقاط النهاية التي لا نتابعها (health, metrics نفسها)
    SKIP_PATHS = {"/metrics", "/health", "/ready", "/live"}

    def __init__(self, app, service_name: str = "unknown"):
        self.app = app
        self.service_name = service_name

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")
        method = scope.get("method", "GET")

        # تخطي نقاط المراقبة
        if path in self.SKIP_PATHS or path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi"):
            await self.app(scope, receive, send)
            return

        if not PROMETHEUS_AVAILABLE:
            await self.app(scope, receive, send)
            return

        # استخراج اسم endpoint (بدون معرّفات ديناميكية)
        endpoint = self._normalize_path(path)

        # زيادة الطلبات قيد التنفيذ
        REQUESTS_IN_FLIGHT.labels(
            service=self.service_name,
            method=method,
            endpoint=endpoint,
        ).inc()

        start_time = time.perf_counter()
        status_code = 500  # افتراضي في حالة الخطأ

        try:
            # اعتراض send لتسجيل status code وحجم الاستجابة
            response_size = 0

            async def send_wrapper(message):
                nonlocal status_code, response_size
                if message["type"] == "http.response.start":
                    status_code = message.get("status", 500)
                elif message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    response_size += len(body)
                await send(message)

            await self.app(scope, receive, send_wrapper)

        except Exception as exc:
            # تسجيل الاستثناء في Sentry إن توفر
            self._capture_exception(exc, endpoint, method)
            raise
        finally:
            # حساب المدة
            duration = time.perf_counter() - start_time

            # تسجيل المقاييس
            status_str = str(status_code)

            REQUEST_COUNT.labels(
                service=self.service_name,
                method=method,
                endpoint=endpoint,
                status_code=status_str,
            ).inc()

            REQUEST_DURATION.labels(
                service=self.service_name,
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            RESPONSE_SIZE.labels(
                service=self.service_name,
                method=method,
                endpoint=endpoint,
            ).observe(response_size)

            # تسجيل الأخطاء (4xx و 5xx)
            if status_code >= 400:
                ERROR_COUNT.labels(
                    service=self.service_name,
                    method=method,
                    endpoint=endpoint,
                    error_class=self._get_error_class(status_code),
                    status_code=status_str,
                ).inc()

            # تقليل الطلبات قيد التنفيذ
            REQUESTS_IN_FLIGHT.labels(
                service=self.service_name,
                method=method,
                endpoint=endpoint,
            ).dec()

    @staticmethod
    def _normalize_path(path: str) -> str:
        """
        تطبيع المسار لاستبدال المعرّفات الديناميكية بأسماء معقولة.
        /api/lands/EG-CAI-01 → /api/lands/{land_id}
        /api/auth/me → /api/auth/me
        """
        parts = path.strip("/").split("/")

        normalized_parts = []
        for i, part in enumerate(parts):
            # إذا كان الجزء يبدو كمعرّف (UUID, رقم, رمز مثل EG-CAI-01)
            if (i > 0 and (
                part.startswith("EG-") or
                part.startswith("user-") or
                "-" in part and i >= 3 or
                part.isdigit() or
                len(part) >= 12  # UUID-like
            )):
                normalized_parts.append("{" + parts[i - 1].rstrip("s") + "_id}")
            else:
                normalized_parts.append(part)

        result = "/" + "/".join(normalized_parts)
        return result if result != "/" else "/"

    @staticmethod
    def _get_error_class(status_code: int) -> str:
        """تصنيف الخطأ حسب كود الحالة."""
        if status_code >= 500:
            return "server_error"
        elif status_code == 429:
            return "rate_limited"
        elif status_code == 401:
            return "unauthorized"
        elif status_code == 403:
            return "forbidden"
        elif status_code == 404:
            return "not_found"
        elif status_code == 422:
            return "validation_error"
        else:
            return "client_error"

    @staticmethod
    def _capture_exception(exc: Exception, endpoint: str, method: str):
        """إرسال الاستثناء لـ Sentry إن توفر."""
        try:
            import sentry_sdk
            if sentry_sdk.Hub.current.client:
                with sentry_sdk.configure_scope(scope=scope_cb):
                    sentry_sdk.capture_exception(exc)
        except Exception:
            pass


def scope_cb(scope):
    """رد اتصال لتعيين بيانات إضافية على Sentry scope."""
    pass


# ──────────────────────────────────────────────────────────────
# 4. دالة الإعداد الرئيسية
# ──────────────────────────────────────────────────────────────

def setup_metrics(
    app,
    service_name: str = "unknown",
    version: str = "1.0.0",
    include_system_metrics: bool = True,
) -> bool:
    """
    إعداد المقاييس لتطبيق FastAPI.

    Args:
        app: تطبيق FastAPI
        service_name: اسم الخدمة (يظهر في تسميات Prometheus)
        version: إصدار الخدمة
        include_system_metrics: تفعيل مقاييس النظام (CPU/RAM)

    Returns:
        True إذا تم الإعداد بنجاح

    الاستخدام:
        from fastapi import FastAPI
        from monitoring.metrics_middleware import setup_metrics

        app = FastAPI()
        setup_metrics(app, service_name="land-service")
    """
    if not PROMETHEUS_AVAILABLE:
        logger.warning("لم يتم إعداد المقاييس — prometheus_client غير مثبت")
        return False

    # 1. إضافة وسيط المقاييس
    app.add_middleware(MetricsMiddleware, service_name=service_name)

    # 2. تعيين معلومات التطبيق
    APP_INFO.info({
        "service": service_name,
        "version": version,
    })

    # 3. إضافة نقطة نهاية /metrics
    from starlette.routing import Route
    from starlette.responses import Response as StarletteResponse

    async def metrics_endpoint(request):
        """نقطة نهاية Prometheus metrics."""
        body = generate_latest(REGISTRY)
        return StarletteResponse(
            content=body,
            media_type=CONTENT_TYPE_LATEST,
        )

    # إضافة المسار إذا لم يكن موجوداً
    existing_paths = [route.path for route in app.routes]
    if "/metrics" not in existing_paths:
        app.routes.append(Route("/metrics", metrics_endpoint))

    # 4. مقاييس النظام (اختياري)
    if include_system_metrics:
        try:
            from prometheus_client import ProcessCollector, PlatformCollector
            ProcessCollector()
            PlatformCollector()
        except Exception as e:
            logger.debug("لم يتم تفعيل مقاييس النظام: %s", e)

    logger.info(
        "تم إعداد المقاييس لـ %s v%s — /metrics",
        service_name, version,
    )
    return True


# ──────────────────────────────────────────────────────────────
# 5. أدوات مساعدة لتتبع عمليات الأعمال
# ──────────────────────────────────────────────────────────────

def track_business_operation(
    service: str,
    operation: str,
    success: bool = True,
):
    """
    تسجيل عملية تجارية/أعمال.

    الاستخدام:
        track_business_operation("land-service", "matchmaking", success=True)
        track_business_operation("auth-service", "login", success=False)
    """
    if not PROMETHEUS_AVAILABLE:
        return
    BUSINESS_OPS.labels(
        service=service,
        operation=operation,
        status="success" if success else "failure",
    ).inc()


def track_llm_request(
    service: str,
    provider: str,
    mode: str,
    duration_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
):
    """
    تسجيل طلب LLM مع الوقت والرموز.

    الاستخدام:
        track_llm_request("prediction-service", "glm", "advisory", 3.5, 500, 2000)
    """
    if not PROMETHEUS_AVAILABLE:
        return
    LLM_DURATION.labels(
        service=service,
        provider=provider,
        mode=mode,
    ).observe(duration_seconds)

    if prompt_tokens:
        LLM_TOKENS.labels(
            service=service,
            provider=provider,
            direction="prompt",
        ).inc(prompt_tokens)

    if completion_tokens:
        LLM_TOKENS.labels(
            service=service,
            provider=provider,
            direction="completion",
        ).inc(completion_tokens)


def track_auth_operation(
    service: str,
    operation: str,  # login, register, refresh, validate
    success: bool = True,
):
    """تسجيل عملية مصادقة."""
    if not PROMETHEUS_AVAILABLE:
        return
    AUTH_OPS.labels(
        service=service,
        operation=operation,
        status="success" if success else "failure",
    ).inc()


class LLMTracker:
    """
    سياقي (context manager) لتتبع طلبات LLM.

    الاستخدام:
        with LLMTracker("prediction-service", "glm", "advisory") as tracker:
            result = call_llm(...)
            tracker.prompt_tokens = 500
            tracker.completion_tokens = 2000
    """

    def __init__(self, service: str, provider: str, mode: str):
        self.service = service
        self.provider = provider
        self.mode = mode
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._start = None

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        if self._start and PROMETHEUS_AVAILABLE:
            duration = time.perf_counter() - self._start
            track_llm_request(
                self.service, self.provider, self.mode, duration,
                self.prompt_tokens, self.completion_tokens,
            )


# ──────────────────────────────────────────────────────────────
# 6. أداة P50/P95/P99 حسابية (بدون Prometheus)
# ──────────────────────────────────────────────────────────────

class LatencyTracker:
    """
    متتبع زمن الاستجابة — يحسب P50/P95/P99 محلياً.

    مفيد لعرض المقاييس في Streamlit أو Logs بدون Prometheus.

    الاستخدام:
        tracker = LatencyTracker()

        # تسجيل أوقات
        tracker.record("GET /api/lands", 0.045)
        tracker.record("GET /api/lands", 0.120)
        tracker.record("POST /api/lands/match", 1.5)

        # استرجاع الإحصائيات
        stats = tracker.get_percentiles("GET /api/lands")
        # {"p50": 0.082, "p95": 0.118, "p99": 0.120, "count": 2, "avg": 0.082}
    """

    def __init__(self, max_samples: int = 10000):
        """
        Args:
            max_samples: الحد الأقصى للعينات المحفوظة لكل endpoint
        """
        self._data: Dict[str, List[float]] = {}
        self._max_samples = max_samples

    def record(self, endpoint: str, duration: float):
        """تسجيل زمن استجابة."""
        if endpoint not in self._data:
            self._data[endpoint] = []

        samples = self._data[endpoint]
        samples.append(duration)

        # تقليم العينات القديمة
        if len(samples) > self._max_samples:
            self._data[endpoint] = samples[-self._max_samples:]

    def get_percentiles(self, endpoint: str) -> Dict[str, Any]:
        """
        حساب P50/P95/P99 لـ endpoint محدد.

        Returns:
            dict مع p50, p95, p99, count, avg, min, max
        """
        samples = self._data.get(endpoint, [])
        if not samples:
            return {
                "p50": 0, "p95": 0, "p99": 0,
                "count": 0, "avg": 0, "min": 0, "max": 0,
            }

        sorted_samples = sorted(samples)
        n = len(sorted_samples)

        def percentile(p: float) -> float:
            idx = int(n * p / 100)
            return sorted_samples[min(idx, n - 1)]

        return {
            "p50": round(percentile(50), 4),
            "p95": round(percentile(95), 4),
            "p99": round(percentile(99), 4),
            "count": n,
            "avg": round(sum(samples) / n, 4),
            "min": round(min(samples), 4),
            "max": round(max(samples), 4),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """إحصائيات جميع endpoints."""
        return {ep: self.get_percentiles(ep) for ep in self._data}

    def clear(self, endpoint: Optional[str] = None):
        """مسح العينات."""
        if endpoint:
            self._data.pop(endpoint, None)
        else:
            self._data.clear()


# ──────────────────────────────────────────────────────────────
# 7. وسيط لوج موحّد (لإرسال Logs لـ Loki)
# ──────────────────────────────────────────────────────────────

def setup_logging_for_loki(
    service_name: str,
    loki_url: str = "http://loki:3100",
    level: int = logging.INFO,
):
    """
    إعداد logging لإرسال السجلات لـ Loki.

    يُضيف handler يُرسل JSON logs إلى Loki /loki/api/v1/push
    متوافق مع Grafana Loki.

    الاستخدام:
        setup_logging_for_loki("land-service")
    """
    import json as json_module

    class LokiHandler(logging.Handler):
        """Handler يُرسل السجلات لـ Loki عبر HTTP."""

        def __init__(self, service: str, url: str):
            super().__init__(level)
            self.service = service
            self.loki_url = url
            self._session = None

        def _get_session(self):
            if self._session is None:
                import requests as req
                self._session = req.Session()
            return self._session

        def emit(self, record):
            try:
                log_entry = {
                    "streams": [{
                        "stream": {
                            "service": self.service,
                            "level": record.levelname,
                            "logger": record.name,
                        },
                        "values": [
                            [str(int(time.time() * 1e9)), self.format(record)]
                        ],
                    }],
                }

                session = self._get_session()
                session.post(
                    f"{self.loki_url}/loki/api/v1/push",
                    json=log_entry,
                    timeout=5,
                )
            except Exception:
                self.handleError(record)

    handler = LokiHandler(service_name, loki_url)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    ))

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    logger.info("تم إعداد Loki logging لـ %s → %s", service_name, loki_url)