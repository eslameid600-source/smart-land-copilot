"""
موجّه LLM الذكي مع Fallback تلقائي — النسخة العربية v1.0
=============================================================
Smart Land Management Copilot — Intelligent LLM Router
========================================================
• يوجّه الطلبات تلقائياً: GLM Cloud → Ollama Local → Mock Fallback
• سلسلة Fallback من 3 مستويات مع تسجيل مفصّل
• دعم التبديل اليدوي (force_provider) للتجربة والاختبار
• إحصائيات الأداء لكل مزوّد
• وضع "الاحتفاظ بالأفضل" — يفضّل المزوّد الأسرع استجابة

سلسلة Fallback:
  1. GLM API (OpenRouter) — أعلى جودة، يحتاج مفتاح API واتصال إنترنت
  2. Ollama Local — نموذج محلي، لا يحتاج إنترنت، يحتاج VRAM كافية
  3. Mock Response — ردود تجريبية ثابتة، تعمل دائماً

متغيرات البيئة:
  LLM_FORCE_PROVIDER  — تجاوز التوجيه التلقائي (glm/ollama/mock/auto)
  LLM_GLAM_ORDER      — ترتيب المزوّدين (الافتراضي: glm,ollama,mock)
  LLM_HEALTH_CHECK    — فحص صحة دوري بالثواني (الافتراضي: 60, 0=معطّل)
"""

import os
import time
import logging
import threading
from typing import Generator, Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 1. أنواع المزوّدين
# ──────────────────────────────────────────────────────────────

class LLMProvider(str, Enum):
    """أنواع مزوّدي LLM."""
    GLM = "glm"               # GLM-5 Turbo عبر OpenRouter
    OLLAMA = "ollama"         # نموذج محلي عبر Ollama
    MOCK = "mock"             # ردود تجريبية ثابتة


@dataclass
class LLMResponse:
    """استجابة موحّدة من أي مزوّد."""
    provider: LLMProvider
    content: str
    response_time_ms: float
    success: bool = True
    error_message: str = ""
    model_name: str = ""
    is_streaming: bool = False
    fallback_used: bool = False


@dataclass
class ProviderHealth:
    """حالة مزوّد."""
    provider: LLMProvider
    is_healthy: bool = True
    consecutive_failures: int = 0
    last_success_time: Optional[float] = None
    last_failure_time: Optional[float] = None
    last_error: str = ""
    total_requests: int = 0
    total_successes: int = 0
    total_failures: int = 0
    avg_response_time_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.total_successes / self.total_requests

    def record_success(self, response_time_ms: float):
        """تسجيل طلب ناجح."""
        self.total_requests += 1
        self.total_successes += 1
        self.consecutive_failures = 0
        self.last_success_time = time.time()
        # تحديث المتوسط المتحرك
        alpha = 0.3
        self.avg_response_time_ms = (
            alpha * response_time_ms + (1 - alpha) * self.avg_response_time_ms
        )

    def record_failure(self, error: str):
        """تسجيل طلب فاشل."""
        self.total_requests += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        self.last_error = error
        if self.consecutive_failures >= 3:
            self.is_healthy = False
            logger.warning(
                "تم وضع علامة 'غير صحي' على %s بعد %d فشل متتالي",
                self.provider.value, self.consecutive_failures,
            )

    def reset_health(self):
        """إعادة تعيين الحالة إلى صحي."""
        self.is_healthy = True
        self.consecutive_failures = 0


# ──────────────────────────────────────────────────────────────
# 2. موّجه LLM الرئيسي
# ──────────────────────────────────────────────────────────────

class LLMRouter:
    """
    موجّه LLM ذكي مع سلسلة Fallback تلقائية.

    الاستخدام الأساسي:
        router = LLMRouter()
        for chunk in router.stream_chat("أبحث عن أرض صناعية...", context_text):
            print(chunk, end="")

    الميزات:
    • توجيه تلقائي: GLM → Ollama → Mock
    • تجاوز المزوّد غير الصحي تلقائياً
    • إحصائيات مفصّلة لكل مزوّد
    • فحص صحة دوري اختياري
    • تبديل يدوي عبر force_provider
    """

    # الحد الأقصى للفشل المتتالي قبل تعطيل المزوّد
    MAX_CONSECUTIVE_FAILURES = 3

    # مدة الحظر بعد تعطيل المزوّد (بالثواني)
    COOLDOWN_PERIOD = 120

    def __init__(
        self,
        force_provider: Optional[str] = None,
        health_check_interval: int = 0,
        auto_start_ollama: bool = False,
    ):
        """
        تهيئة الموجّه.

        Args:
            force_provider: تجاوز تلقائي (glm/ollama/mock/auto)
            health_check_interval: فحص صحة دوري بالثواني (0=معطّل)
            auto_start_ollama: محاولة تشغيل Ollama تلقائياً
        """
        # تحديد ترتيب المزوّدين
        self._force_provider = self._parse_force_provider(force_provider)
        self._provider_order = self._parse_provider_order()

        # حالة المزوّدين
        self._health: Dict[LLMProvider, ProviderHealth] = {
            p: ProviderHealth(provider=p) for p in LLMProvider
        }

        # مثيلات المزوّدين (تهيئة كسول)
        self._ollama_service = None
        self._glm_available = None
        self._lock = threading.Lock()

        # تهيئة المزوّدين
        self._init_glm()
        self._init_ollama(auto_start_ollama)

        # فحص الصحة الدوري
        self._health_check_interval = health_check_interval or int(
            os.environ.get("LLM_HEALTH_CHECK", "0")
        )
        self._health_thread: Optional[threading.Thread] = None
        self._stop_health_check = threading.Event()

        if self._health_check_interval > 0:
            self._start_health_check()

        logger.info(
            "تم تهيئة LLMRouter — ترتيب: %s, تجاوز: %s",
            [p.value for p in self._provider_order],
            self._force_provider or "auto",
        )

    # ──────────────────────────────────────────────────────────
    # 2.1 التهيئة
    # ──────────────────────────────────────────────────────────

    def _parse_force_provider(self, force: Optional[str]) -> Optional[LLMProvider]:
        """تحليل متغير تجاوز المزوّد."""
        if force is None:
            force = os.environ.get("LLM_FORCE_PROVIDER", "").lower().strip()
        if force in ("glm", "auto", ""):
            return None
        try:
            return LLMProvider(force)
        except ValueError:
            logger.warning("قيمة LLM_FORCE_PROVIDER غير صالحة: %s", force)
            return None

    def _parse_provider_order(self) -> List[LLMProvider]:
        """تحليل ترتيب المزوّدين من متغير البيئة."""
        order_str = os.environ.get("LLM_GLAM_ORDER", "glm,ollama,mock")
        order = []
        for name in order_str.split(","):
            name = name.strip().lower()
            try:
                order.append(LLMProvider(name))
            except ValueError:
                logger.warning("مزوّد غير معروف في ترتيب Fallback: %s", name)
        # التأكد من وجود جميع المزوّدين
        for p in LLMProvider:
            if p not in order:
                order.append(p)
        return order

    def _init_glm(self):
        """فحص توفر GLM API."""
        api_key = os.environ.get("GLM_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))
        if api_key:
            self._glm_available = True
            self._health[LLMProvider.GLM].is_healthy = True
            logger.info("GLM API متاح (مفتاح موجود)")
        else:
            self._glm_available = False
            self._health[LLMProvider.GLM].is_healthy = False
            self._health[LLMProvider.GLM].last_error = "مفتاح API غير موجود"
            logger.info("GLM API غير متاح — لا يوجد مفتاح API")

    def _init_ollama(self, auto_start: bool):
        """تهيئة خدمة Ollama (كسول)."""
        try:
            from core.ai.llm.ollama_service import LocalLLMService, OllamaInstaller
            self._ollama_service = LocalLLMService(auto_start=auto_start)

            if self._ollama_service.is_available:
                self._health[LLMProvider.OLLAMA].is_healthy = True
                logger.info(
                    "Ollama متاح — النموذج: %s",
                    self._ollama_service.model,
                )
            else:
                self._health[LLMProvider.OLLAMA].is_healthy = False
                self._health[LLMProvider.OLLAMA].last_error = "Ollama لا يعمل أو لا يوجد نموذج"
                logger.info("Ollama غير متاح — سيتم استخدامه كـ Fallback فقط")

        except ImportError:
            self._ollama_service = None
            self._health[LLMProvider.OLLAMA].is_healthy = False
            self._health[LLMProvider.OLLAMA].last_error = "وحدة ollama_service غير مثبتة"
            logger.info("وحدة ollama_service غير متاحة")

    # ──────────────────────────────────────────────────────────
    # 2.2 دوال التدفق العامة
    # ──────────────────────────────────────────────────────────

    def stream_chat(
        self,
        user_query: str,
        context: str,
        temperature: float = 0.4,
    ) -> Generator[str, None, None]:
        """
        محادثة عادية مع سياق الأراضي — تدفق مع Fallback تلقائي.

        يوجّه الطلب تلقائياً: GLM → Ollama → Mock

        Args:
            user_query: استعلام المستثمر
            context: نص سياق الأراضي المسترجعة
            temperature: درجة الحرارة

        Yields:
            أجزاء النص المتدفقة
        """
        yield from self._stream_with_fallback(
            mode="chat",
            user_query=user_query,
            context=context,
            temperature=temperature,
        )

    def stream_matchmaking(
        self,
        criteria_summary: str,
        context_text: str,
        temperature: float = 0.4,
    ) -> Generator[str, None, None]:
        """
        تقرير المطابقة الاستباقية — تدفق مع Fallback تلقائي.

        Args:
            criteria_summary: ملخص شروط المستثمر
            context_text: نص نتائج محرك المطابقة
            temperature: درجة الحرارة

        Yields:
            أجزاء النص المتدفقة
        """
        yield from self._stream_with_fallback(
            mode="matchmaking",
            criteria_summary=criteria_summary,
            context_text=context_text,
            temperature=temperature,
        )

    def stream_advisory_report(
        self,
        criteria_summary: str,
        match_context: str,
        temperature: float = 0.3,
    ) -> Generator[str, None, None]:
        """
        تقرير الجدوى الاستشاري الشامل — تدفق مع Fallback تلقائي.

        Args:
            criteria_summary: ملخص شروط المستثمر
            match_context: سياق نتائج المطابقة التفصيلي
            temperature: درجة الحرارة (0.3 للدقة)

        Yields:
            أجزاء النص المتدفقة
        """
        yield from self._stream_with_fallback(
            mode="advisory",
            criteria_summary=criteria_summary,
            context_text=match_context,
            temperature=temperature,
        )

    def chat_completion(
        self,
        user_query: str,
        context: str,
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> str:
        """
        محادثة عادية — رد كامل مع Fallback تلقائي.

        Returns:
            نص الرد الكامل
        """
        return self._complete_with_fallback(
            mode="chat",
            user_query=user_query,
            context=context,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ──────────────────────────────────────────────────────────
    # 2.3 محرك Fallback
    # ──────────────────────────────────────────────────────────

    def _stream_with_fallback(
        self,
        mode: str,
        **kwargs,
    ) -> Generator[str, None, None]:
        """
        محرك التدفق مع سلسلة Fallback.

        يجرب كل مزوّد بالترتيب حتى ينجح أحدهم.
        """
        # إذا كان هناك تجاوز يدوي، استخدمه فقط
        if self._force_provider is not None:
            yield from self._try_stream_provider(self._force_provider, mode, **kwargs)
            return

        # تجربة المزوّدين بالترتيب
        for provider in self._provider_order:
            health = self._health[provider]

            # تجاوز المزوّد غير الصحي
            if not health.is_healthy:
                # التحقق من انتهاء فترة الحظر
                if (health.last_failure_time and
                    time.time() - health.last_failure_time > self.COOLDOWN_PERIOD):
                    health.reset_health()
                    logger.info("إعادة تنشيط مزوّد %s بعد انتهاء فترة الحظر", provider.value)
                else:
                    logger.debug(
                        "تجاوز %s — غير صحي (فشل متتالي: %d)",
                        provider.value, health.consecutive_failures,
                    )
                    continue

            # محاولة المزوّد
            has_content = False
            start_time = time.time()

            try:
                for chunk in self._try_stream_provider(provider, mode, **kwargs):
                    if chunk:
                        has_content = True
                        yield chunk

                # نجاح
                elapsed = (time.time() - start_time) * 1000
                health.record_success(elapsed)
                logger.info(
                    "%s نجح في %.0f ms (وضع: %s)",
                    provider.value.upper(), elapsed, mode,
                )
                return  # نجح المزوّد — توقف

            except Exception as e:
                elapsed = (time.time() - start_time) * 1000
                health.record_failure(str(e))
                logger.warning(
                    "%s فشل بعد %.0f ms: %s",
                    provider.value.upper(), elapsed, e,
                )
                if has_content:
                    # إذا كان قد أرسل بعض المحتوى، لا ننتقل للمزوّد التالي
                    yield (
                        f"\n\n⚠️ انقطع الاتصال بـ {provider.value.upper()}. "
                        "لم يتم إكمال الرد.\n"
                    )
                    return

        # جميع المزوّدين فشلوا
        yield self._emergency_fallback(mode)

    def _try_stream_provider(
        self,
        provider: LLMProvider,
        mode: str,
        **kwargs,
    ) -> Generator[str, None, None]:
        """محاولة التدفق من مزوّد محدد."""

        if provider == LLMProvider.GLM:
            yield from self._stream_glm(mode, **kwargs)

        elif provider == LLMProvider.OLLAMA:
            if self._ollama_service is None or not self._ollama_service.is_available:
                # محاولة إعادة التهيئة
                self._init_ollama(auto_start=False)
                if self._ollama_service is None or not self._ollama_service.is_available:
                    raise ConnectionError("Ollama غير متاح")
            yield from self._stream_ollama(mode, **kwargs)

        elif provider == LLMProvider.MOCK:
            yield from self._stream_mock(mode, **kwargs)

    def _stream_glm(self, mode: str, **kwargs) -> Generator[str, None, None]:
        """التدفق من GLM API."""
        from core.ai.llm.glm_client import (
            stream_matchmaking_api as glm_stream_matchmaking,
            stream_advisory_report as glm_stream_advisory,
        )

        if mode == "chat":
            # GLM client لا يحتوي على stream_chat — نستخدم call_glm_api
            from core.ai.llm.glm_client import call_glm_api
            result = call_glm_api(
                user_query=kwargs.get("user_query", ""),
                context_text=kwargs.get("context", ""),
                temperature=kwargs.get("temperature", 0.4),
            )
            yield result

        elif mode == "matchmaking":
            yield from glm_stream_matchmaking(
                criteria_summary=kwargs.get("criteria_summary", ""),
                context_text=kwargs.get("context_text", ""),
                temperature=kwargs.get("temperature", 0.4),
            )

        elif mode == "advisory":
            yield from glm_stream_advisory(
                criteria_summary=kwargs.get("criteria_summary", ""),
                match_context=kwargs.get("context_text", ""),
                temperature=kwargs.get("temperature", 0.3),
            )

    def _stream_ollama(self, mode: str, **kwargs) -> Generator[str, None, None]:
        """التدفق من Ollama."""
        svc = self._ollama_service
        if svc is None:
            raise ConnectionError("خدمة Ollama غير مهيأة")

        temperature = kwargs.get("temperature", 0.4)

        if mode == "chat":
            yield from svc.stream_chat(
                user_query=kwargs.get("user_query", ""),
                context=kwargs.get("context", ""),
                temperature=temperature,
            )
        elif mode == "matchmaking":
            yield from svc.stream_matchmaking(
                criteria_summary=kwargs.get("criteria_summary", ""),
                context_text=kwargs.get("context_text", ""),
                temperature=temperature,
            )
        elif mode == "advisory":
            yield from svc.stream_advisory_report(
                criteria_summary=kwargs.get("criteria_summary", ""),
                match_context=kwargs.get("context_text", ""),
                temperature=temperature,
            )

    def _stream_mock(self, mode: str, **kwargs) -> Generator[str, None, None]:
        """التدفق من الردود التجريبية."""
        from core.ai.llm.glm_client import (
            _mock_response,
            _mock_matchmaking_response,
            _mock_advisory_report,
            _chunk_text,
        )

        if mode == "chat":
            text = _mock_response(
                kwargs.get("user_query", ""), kwargs.get("context", "")
            )
        elif mode == "matchmaking":
            text = _mock_matchmaking_response(
                kwargs.get("criteria_summary", ""), kwargs.get("context_text", "")
            )
        elif mode == "advisory":
            text = _mock_advisory_report(
                kwargs.get("criteria_summary", ""), kwargs.get("context_text", "")
            )
        else:
            text = "وضع غير معروف"

        for chunk in _chunk_text(text):
            yield chunk

    def _complete_with_fallback(
        self,
        mode: str,
        **kwargs,
    ) -> str:
        """رد كامل مع Fallback (بدون تدفق)."""
        providers = [self._force_provider] if self._force_provider else self._provider_order

        for provider in providers:
            if not self._health[provider].is_healthy:
                continue
            try:
                start_time = time.time()

                if provider == LLMProvider.GLM:
                    from core.ai.llm.glm_client import call_glm_api
                    result = call_glm_api(
                        user_query=kwargs.get("user_query", ""),
                        context_text=kwargs.get("context", ""),
                        temperature=kwargs.get("temperature", 0.4),
                        max_tokens=kwargs.get("max_tokens", 2048),
                    )
                elif provider == LLMProvider.OLLAMA:
                    if self._ollama_service and self._ollama_service.is_available:
                        result = self._ollama_service.chat_completion(
                            user_query=kwargs.get("user_query", ""),
                            context=kwargs.get("context", ""),
                            temperature=kwargs.get("temperature", 0.4),
                            max_tokens=kwargs.get("max_tokens", 2048),
                        )
                    else:
                        raise ConnectionError("Ollama غير متاح")
                elif provider == LLMProvider.MOCK:
                    from core.ai.llm.glm_client import _mock_response
                    result = _mock_response(
                        kwargs.get("user_query", ""), kwargs.get("context", "")
                    )
                else:
                    continue

                elapsed = (time.time() - start_time) * 1000
                self._health[provider].record_success(elapsed)
                return result

            except Exception as e:
                self._health[provider].record_failure(str(e))
                logger.warning("فشل %s: %s", provider.value, e)

        return self._emergency_fallback(mode)

    @staticmethod
    def _emergency_fallback(mode: str) -> str:
        """رد طوارئ عندما يفشل كل شيء."""
        return (
            "⚠️ جميع خدمات الذكاء الاصطناعي غير متاحة حالياً.\n\n"
            "**الخدمات المطلوبة:**\n"
            "1. GLM API — حدّث مفتاح GLM_API_KEY\n"
            "2. Ollama — شغّله: ollama serve && ollama pull qwen2.5:7b\n\n"
            "يرجى المحاولة مرة أخرى لاحقاً.\n\n"
            "---\n"
            "*إخلاء مسؤولية: تقرير مُولَّد بالذكاء الاصطناعي. تحقق من NUCA/GAFI.*"
        )

    # ──────────────────────────────────────────────────────────
    # 2.4 Agent API — Function Calling مع GLM-5.2-turbo
    # ──────────────────────────────────────────────────────────

    def call_agent_api(
        self,
        messages: List[dict],
        tools: List[dict],
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> dict:
        """
        استدعاء API مع دعم Function Calling للوكيل الذكي.

        يُرسل رسائل + تعريفات الأدوات (tools) و tool_choice: auto
        إلى GLM-5.2-turbo (أو الإصدار المحدد في GLM_MODEL).

        Args:
            messages: قائمة الرسائل [{role, content}, ...] تتضمن
                      رسائل الأداة (role: "tool") أيضاً
            tools: تعريفات الأدوات بصيغة OpenAI Function Calling
            temperature: درجة الحرارة
            max_tokens: الحد الأقصى لل_tokens

        Returns:
            {
                "message": {
                    "role": "assistant",
                    "content": str | None,
                    "tool_calls": [{"id", "type", "function": {"name", "arguments"}}] | None,
                },
                "stop_reason": "tool_calls" | "end_turn" | "max_tokens" | "human_intervention",
            }

        معالجة stop_reason:
          • "tool_calls" — النموذج يريد استدعاء أداة → يُنفَّذ ويُعاد
          • "end_turn" — رد نهائي نصي → يُعرض للمستخدم
          • "max_tokens" — الرد طويل جداً → يُقتطع (يمكن زيادة max_tokens)
          • "human_intervention" — النموذج يقرر أن الطلب يحتاج وكيل بشري
        """
        import requests as _requests

        config = {
            "api_key": os.environ.get("GLM_API_KEY", os.environ.get("OPENROUTER_API_KEY", "")),
            "base_url": os.environ.get("GLM_BASE_URL", "https://openrouter.ai/api/v1"),
            "model": os.environ.get("GLM_MODEL", "glm-5.2-turbo"),
        }

        if not config["api_key"]:
            logger.warning("call_agent_api: لا يوجد مفتاح API — رد تجريبي")
            return {
                "message": {
                    "role": "assistant",
                    "content": "عذراً، مفتاح API غير متاح. يرجى تعيين GLM_API_KEY.",
                },
                "stop_reason": "end_turn",
            }

        payload = {
            "model": config["model"],
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        start_time = time.time()

        try:
            resp = _requests.post(
                f"{config['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")

            # تحويل finish_reason إلى stop_reason
            stop_reason = "end_turn"
            if finish_reason == "tool_calls":
                stop_reason = "tool_calls"
            elif finish_reason == "length":
                stop_reason = "max_tokens"
            elif finish_reason == "stop" and not message.get("content"):
                # stop بدون محتوى قد يعني نهاية صامتة
                stop_reason = "end_turn"

            # فحص خاص: إذا الرد يحتوي على "إنساني" أو "تواصل مع الدعم"
            # → يشير إلى أن الوكيل يريد تحويل للوكيل البشري
            content = message.get("content", "")
            if content and any(kw in content for kw in [
                "تواصل مع فريق الدعم", "human agent", "وكيل بشري",
                "محامي متخصص", "استشارة قانونية متخصصة",
            ]):
                stop_reason = "human_intervention"

            elapsed = (time.time() - start_time) * 1000
            self._health[LLMProvider.GLM].record_success(elapsed)
            logger.info(
                "call_agent_api نجح — stop_reason: %s (%.0f ms)",
                stop_reason, elapsed,
            )

            return {
                "message": message,
                "stop_reason": stop_reason,
            }

        except _requests.exceptions.RequestException as e:
            elapsed = (time.time() - start_time) * 1000
            self._health[LLMProvider.GLM].record_failure(str(e))
            logger.error("call_agent_api فشل: %s", e)

            # Fallback لـ Ollama (إذا كان متاحاً)
            if self._ollama_service and self._ollama_service.is_available:
                logger.info("call_agent_api: محاولة Fallback لـ Ollama")
                try:
                    # Ollama يدعم tools أيضاً
                    ollama_result = self._ollama_agent_fallback(messages, tools, temperature)
                    return ollama_result
                except Exception as ollama_err:
                    logger.warning("call_agent_api: Ollama Fallback فشل: %s", ollama_err)

            return {
                "message": {
                    "role": "assistant",
                    "content": f"حدث خطأ في الاتصال: {e}. يرجى المحاولة مرة أخرى.",
                },
                "stop_reason": "end_turn",
            }

    def _ollama_agent_fallback(
        self,
        messages: List[dict],
        tools: List[dict],
        temperature: float,
    ) -> dict:
        """
        محاولة Ollama كـ Fallback للـ Agent API.

        Ollama يدعم tool calling في الإصدارات الحديثة.
        إذا لم يكن مدعوماً، يُرجع رداً نصياً عادياً.
        """
        if self._ollama_service is None or not self._ollama_service.is_available:
            raise ConnectionError("Ollama غير متاح")

        try:
            # محاولة مع tools
            result = self._ollama_service.chat_completion(
                # Ollama لا يدعم tools في كل الإصدارات
                # نستخدم system prompt مع وصف الأدوات كـ fallback
                user_query="[Agent Mode] " + str(
                    [m.get("content", "") for m in messages if m["role"] == "user"][-1:]
                ),
                context=json.dumps(
                    [t["function"] for t in tools], ensure_ascii=False
                ),
                temperature=temperature,
                max_tokens=2048,
            )
            return {
                "message": {
                    "role": "assistant",
                    "content": result,
                },
                "stop_reason": "end_turn",
            }
        except Exception as e:
            logger.warning("Ollama agent fallback فشل: %s", e)
            raise

    # ──────────────────────────────────────────────────────────
    # 2.5 فحص الصحة الدوري
    # ──────────────────────────────────────────────────────────

    def _start_health_check(self):
        """بدء فحص الصحة الدوري في خيط منفصل."""
        def _health_loop():
            while not self._stop_health_check.is_set():
                self._stop_health_check.wait(self._health_check_interval)
                if self._stop_health_check.is_set():
                    break
                self._perform_health_check()

        self._health_thread = threading.Thread(
            target=_health_loop, daemon=True, name="llm-health-check"
        )
        self._health_thread.start()
        logger.info(
            "بدء فحص الصحة الدوري (كل %d ثانية)", self._health_check_interval
        )

    def _perform_health_check(self):
        """فحص صحة جميع المزوّدين."""
        # فحص GLM
        if not self._health[LLMProvider.GLM].is_healthy:
            api_key = os.environ.get("GLM_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))
            if api_key:
                try:
                    import requests
                    base_url = os.environ.get("GLM_BASE_URL", "https://openrouter.ai/api/v1")
                    resp = requests.get(f"{base_url}/models", timeout=10, headers={
                        "Authorization": f"Bearer {api_key}",
                    })
                    if resp.status_code in (200, 401):
                        # حتى 401 يعني أن الخدمة تعمل (مفتاح خاطئ فقط)
                        self._health[LLMProvider.GLM].reset_health()
                        logger.info("GLM API عاد للعمل")
                except Exception:
                    pass

        # فحص Ollama
        if not self._health[LLMProvider.OLLAMA].is_healthy and self._ollama_service:
            try:
                health = self._ollama_service.check_health()
                if health.is_running:
                    self._health[LLMProvider.OLLAMA].reset_health()
                    logger.info("Ollama عاد للعمل")
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────
    # 2.6 التحكم اليدوي
    # ──────────────────────────────────────────────────────────

    def set_force_provider(self, provider: Optional[str]):
        """
        تعيين مزوّد محدد أو العودة للتوجيه التلقائي.

        Args:
            provider: glm / ollama / mock / auto (أو None للتلقائي)
        """
        self._force_provider = self._parse_force_provider(provider)
        logger.info("تم تغيير المزوّد المُجبر إلى: %s", self._force_provider or "auto")

    def set_provider_order(self, order: List[str]):
        """
        تغيير ترتيب Fallback.

        Args:
            order: قائمة مثل ["ollama", "glm", "mock"]
        """
        env_str = ",".join(order)
        self._provider_order = self._parse_provider_order.__func__(self, env_str)
        # إعادة تعيين باستخدام الطريقة الصحيحة
        new_order = []
        for name in order:
            try:
                new_order.append(LLMProvider(name.lower().strip()))
            except ValueError:
                pass
        for p in LLMProvider:
            if p not in new_order:
                new_order.append(p)
        self._provider_order = new_order
        logger.info("تم تغيير ترتيب المزوّدين إلى: %s", [p.value for p in self._provider_order])

    def reset_health(self, provider: Optional[str] = None):
        """إعادة تعيين حالة مزوّد (أو الكل)."""
        if provider:
            try:
                p = LLMProvider(provider)
                self._health[p].reset_health()
                logger.info("تم إعادة تعيين صحة %s", p.value)
            except ValueError:
                pass
        else:
            for h in self._health.values():
                h.reset_health()
            logger.info("تم إعادة تعيين صحة جميع المزوّدين")

    # ──────────────────────────────────────────────────────────
    # 2.7 الإحصائيات والتقارير
    # ──────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """
        تقرير حالة شامل للموجّه.

        مفيد لصفحة الإعدادات في Streamlit.
        """
        providers_status = {}
        for p, h in self._health.items():
            providers_status[p.value] = {
                "is_healthy": h.is_healthy,
                "success_rate": round(h.success_rate * 100, 1),
                "total_requests": h.total_requests,
                "total_successes": h.total_successes,
                "total_failures": h.total_failures,
                "consecutive_failures": h.consecutive_failures,
                "avg_response_time_ms": round(h.avg_response_time_ms, 1),
                "last_error": h.last_error,
                "last_success": (
                    time.strftime("%H:%M:%S", time.localtime(h.last_success_time))
                    if h.last_success_time else "لم ينجح بعد"
                ),
            }

        # تحديد المزوّد النشط
        active_provider = "mock"
        if self._force_provider:
            active_provider = self._force_provider.value
        else:
            for p in self._provider_order:
                if self._health[p].is_healthy:
                    active_provider = p.value
                    break

        return {
            "active_provider": active_provider,
            "provider_order": [p.value for p in self._provider_order],
            "force_provider": self._force_provider.value if self._force_provider else "auto",
            "providers": providers_status,
            "ollama_diagnostics": (
                self._ollama_service.get_diagnostics() if self._ollama_service else None
            ),
            "glm_available": self._glm_available,
            "health_check_running": self._health_thread is not None and self._health_thread.is_alive(),
        }

    def get_provider_stats(self) -> Dict[str, Dict[str, Any]]:
        """إحصائيات كل مزوّد."""
        result = {}
        for p, h in self._health.items():
            result[p.value] = {
                "total_requests": h.total_requests,
                "success_rate": f"{h.success_rate * 100:.1f}%",
                "avg_response_ms": f"{h.avg_response_time_ms:.0f}ms",
                "is_healthy": h.is_healthy,
            }
        return result

    # ──────────────────────────────────────────────────────────
    # التنظيف
    # ──────────────────────────────────────────────────────────

    def shutdown(self):
        """إيقاف فحص الصحة الدوري."""
        self._stop_health_check.set()
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=5)
        logger.info("تم إيقاف LLMRouter")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()

    def __repr__(self) -> str:
        active = "?"
        if self._force_provider:
            active = self._force_provider.value
        else:
            for p in self._provider_order:
                if self._health[p].is_healthy:
                    active = p.value
                    break
        return f"LLMRouter(active={active}, order={[p.value for p in self._provider_order]})"