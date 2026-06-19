"""
خدمة LLM المحلية عبر Ollama — النسخة العربية v1.0
=====================================================
Smart Land Management Copilot — Local Ollama LLM Service
=========================================================
• تشغيل نموذج مفتوح المصدر محلياً (Qwen2.5-7B / Llama-3-8B)
• واجهة متوافقة مع GLM Client (stream_chat, stream_matchmaking, stream_advisory_report)
• تثبيت وتشغيل Ollama تلقائياً عبر subprocess أو Docker
• دعم التدفق (streaming) للردود الطويلة

متغيرات البيئة:
  OLLAMA_BASE_URL   — رابط Ollama (الافتراضي: http://localhost:11434)
  OLLAMA_MODEL      — اسم النموذج (الافتراضي: qwen2.5:7b)
  OLLAMA_TIMEOUT    — مهلة الاستجابة بالثواني (الافتراضي: 180)
  OLLAMA_NUM_CTX    — طول السياق (الافتراضي: 8192)
  OLLAMA_AUTO_INSTALL — تثبيت Ollama تلقائياً (الافتراضي: true)
"""

import os
import sys
import json
import logging
import platform
import subprocess
import time
import shutil
from typing import Generator, Optional, List, Dict, Any
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 1. الإعدادات الافتراضية
# ──────────────────────────────────────────────────────────────

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"
FALLBACK_MODELS = [
    "qwen2.5:7b",       # أفضل دعم للعربية بين النماذج الصغيرة
    "llama3:8b",         # قوي عام
    "mistral:7b",        # خفيف وسريع
    "gemma2:9b",         # دعم جيد للعربية
]

# أسماء النماذج المقبولة (للتحقق من صحة الإدخال)
VALID_MODELS = {
    "qwen2.5:7b": "Qwen 2.5 — 7B (أفضل دعم عربي)",
    "qwen2.5:14b": "Qwen 2.5 — 14B (دقة أعلى، يحتاج VRAM أكثر)",
    "llama3:8b": "Llama 3 — 8B (قوي متعدد اللغات)",
    "llama3.1:8b": "Llama 3.1 — 8B (تحسينات على Llama 3)",
    "mistral:7b": "Mistral — 7B (خفيف وسريع)",
    "gemma2:9b": "Gemma 2 — 9B (Google، دعم عربي جيد)",
    "phi3:mini": "Phi-3 Mini — 3.8B (خفيف جداً، Intel)",
    "deepseek-r1:7b": "DeepSeek R1 — 7B (تفكير متقدم)",
}


# ──────────────────────────────────────────────────────────────
# 2. نماذج البيانات
# ──────────────────────────────────────────────────────────────

@dataclass
class OllamaModelInfo:
    """معلومات عن نموذج Ollama."""
    name: str
    size_gb: float
    quantization: str
    family: str
    parameter_size: str
    is_available: bool = False


@dataclass
class OllamaHealthStatus:
    """حالة Ollama Service."""
    is_running: bool
    version: str = ""
    models_available: List[str] = field(default_factory=list)
    total_vram_gb: float = 0.0
    error_message: str = ""


# ──────────────────────────────────────────────────────────────
# 3. مدير تثبيت Ollama
# ──────────────────────────────────────────────────────────────

class OllamaInstaller:
    """
    مدير تثبيت وتشغيل Ollama.

    يدعم ثلاثة أساليب:
    1. Docker — إذا كان Docker متاحاً (docker run ollama/ollama)
    2. تثبيت محلي — تحميل وتثبيت Ollama CLI على النظام
    3. التحقق فقط — افتراض أن Ollama مثبت بالفعل
    """

    @staticmethod
    def is_docker_available() -> bool:
        """التحقق من توفر Docker."""
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def is_ollama_installed() -> bool:
        """التحقق من تثبيت Ollama على النظام."""
        return shutil.which("ollama") is not None

    @staticmethod
    def install_ollama_linux() -> bool:
        """
        تثبيت Ollama على Linux عبر السكريبت الرسمي.
        يعمل على Ubuntu/Debian/CentOS/RHEL.
        """
        logger.info("بدء تثبيت Ollama على Linux...")

        try:
            # تحميل سكريبت التثبيت الرسمي
            curl_result = subprocess.run(
                ["curl", "-fsSL", "https://ollama.com/install.sh"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if curl_result.returncode != 0:
                logger.error("فشل تحميل سكريبت تثبيت Ollama: %s", curl_result.stderr)
                return False

            # تشغيل سكريبت التثبيت
            install_result = subprocess.run(
                ["sh", "-c", curl_result.stdout],
                capture_output=True,
                text=True,
                timeout=300,  # 5 دقائق كحد أقصى
            )

            if install_result.returncode != 0:
                logger.error("فشل تثبيت Ollama: %s", install_result.stderr)
                return False

            logger.info("تم تثبيت Ollama بنجاح")
            return True

        except (subprocess.TimeoutExpired, Exception) as e:
            logger.error("خطأ أثناء تثبيت Ollama: %s", e)
            return False

    @staticmethod
    def start_ollama_process() -> Optional[subprocess.Popen]:
        """
        تشغيل Ollama كعملية خلفية.
        يُرجع كائن Popen إذا نجح، أو None إذا فشل.
        """
        if not OllamaInstaller.is_ollama_installed():
            logger.warning("Ollama غير مثبت على النظام")
            return None

        try:
            # تشغيل Ollama في الخلفية
            # --host 0.0.0.0 للسماح بالوصول من حاويات Docker الأخرى
            process = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            logger.info("تم تشغيل Ollama (PID: %d) — بانتظار الجاهزية...", process.pid)

            # الانتظار حتى يصبح Ollama جاهزاً (حد أقصى 30 ثانية)
            base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)
            for i in range(30):
                time.sleep(1)
                try:
                    resp = requests.get(f"{base_url}/api/tags", timeout=3)
                    if resp.status_code == 200:
                        logger.info("Ollama جاهز بعد %d ثوانٍ", i + 1)
                        return process
                except requests.ConnectionError:
                    continue

            logger.warning("انتهت مهلة انتظار Ollama (30 ثانية)")
            process.terminate()
            return None

        except FileNotFoundError:
            logger.error("أمر 'ollama' غير موجود")
            return None
        except Exception as e:
            logger.error("خطأ أثناء تشغيل Ollama: %s", e)
            return None

    @staticmethod
    def ensure_ollama_running(
        use_docker: bool = False,
        docker_container_name: str = "smart-land-ollama",
    ) -> bool:
        """
        التأكد من تشغيل Ollama بأي طريقة ممكنة.

        سلسلة المحاولات:
        1. التحقق من أن Ollama يعمل بالفعل
        2. محاولة تشغيله محلياً إذا كان مثبتاً
        3. تثبيته وتشغيله (Linux فقط)
        4. تجربة Docker إذا كان متاحاً

        Returns:
            True إذا كان Ollama يعمل بنجاح
        """
        base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)

        # 1. التحقق من أن Ollama يعمل بالفعل
        if OllamaInstaller._check_health(base_url).is_running:
            logger.info("Ollama يعمل بالفعل")
            return True

        # 2. محاولة تشغيله محلياً
        if OllamaInstaller.is_ollama_installed():
            process = OllamaInstaller.start_ollama_process()
            if process is not None:
                return True

        # 3. التثبيت التلقائي (إذا كان مسموحاً)
        auto_install = os.environ.get("OLLAMA_AUTO_INSTALL", "true").lower() == "true"
        if auto_install and platform.system() == "Linux":
            logger.info("محاولة تثبيت Ollama تلقائياً...")
            if OllamaInstaller.install_ollama_linux():
                process = OllamaInstaller.start_ollama_process()
                if process is not None:
                    return True

        # 4. تجربة Docker
        if use_docker and OllamaInstaller.is_docker_available():
            logger.info("محاولة تشغيل Ollama عبر Docker...")
            try:
                # التحقق من وجود الحاوية بالفعل
                check = subprocess.run(
                    ["docker", "ps", "-a", "--filter", f"name={docker_container_name}", "--format", "{{.Names}}"],
                    capture_output=True, text=True, timeout=10,
                )
                if docker_container_name in check.stdout:
                    # تشغيل الحاوية الموجودة
                    subprocess.run(
                        ["docker", "start", docker_container_name],
                        capture_output=True, text=True, timeout=30,
                    )
                else:
                    # إنشاء حاوية جديدة
                    subprocess.run(
                        [
                            "docker", "run", "-d",
                            "--name", docker_container_name,
                            "-p", "11434:11434",
                            "-v", "ollama_data:/root/.ollama",
                            "ollama/ollama",
                        ],
                        capture_output=True, text=True, timeout=120,
                    )

                # الانتظار حتى يصبح جاهزاً
                for i in range(30):
                    time.sleep(1)
                    if OllamaInstaller._check_health(base_url).is_running:
                        logger.info("Ollama يعمل عبر Docker")
                        return True

            except Exception as e:
                logger.error("فشل تشغيل Ollama عبر Docker: %s", e)

        logger.error("لم يتمكن من تشغيل Ollama بأي طريقة")
        return False

    @staticmethod
    def _check_health(base_url: str) -> OllamaHealthStatus:
        """التحقق من صحة Ollama."""
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                return OllamaHealthStatus(
                    is_running=True,
                    models_available=models,
                )
        except requests.ConnectionError:
            pass
        except Exception as e:
            logger.debug("فشل فحص صحة Ollama: %s", e)

        return OllamaHealthStatus(is_running=False)


# ──────────────────────────────────────────────────────────────
# 4. خدمة LLM المحلية
# ──────────────────────────────────────────────────────────────

class LocalLLMService:
    """
    خدمة LLM المحلية عبر Ollama.

    توفر واجهة متوافقة مع GLM Client:
    - stream_chat(user_query, context) — محادثة عادية مع سياق الأراضي
    - stream_matchmaking(criteria, context) — تقرير المطابقة الاستباقية
    - stream_advisory_report(criteria, context) — تقرير الجدوى الاستشاري

    الميزات:
    • تدفق حقيقي (streaming) من Ollama
    • إعادة محاولة تلقائية عند الفشل
    • تحميل تلقائي للنموذج إذا لم يكن موجوداً
    • إحصائيات الاستخدام
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        num_ctx: Optional[int] = None,
        auto_start: bool = True,
    ):
        """
        تهيئة خدمة Ollama المحلية.

        Args:
            base_url: رابط Ollama API (الافتراضي: http://localhost:11434)
            model: اسم النموذج (الافتراضي: qwen2.5:7b)
            timeout: مهلة الاستجابة بالثواني (الافتراضي: 180)
            num_ctx: طول سياق النموذج (الافتراضي: 8192)
            auto_start: محاولة تشغيل Ollama تلقائياً إذا لم يكن يعمل
        """
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
        self.timeout = timeout or int(os.environ.get("OLLAMA_TIMEOUT", "180"))
        self.num_ctx = num_ctx or int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
        self._is_available = False
        self._health: Optional[OllamaHealthStatus] = None
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_tokens_estimated": 0,
            "fallback_used": 0,
            "model_pulls": 0,
        }
        # استيراد البرومبتات من GLM Client
        self._system_prompts = None

        if auto_start:
            self._initialize()

    def _initialize(self):
        """تهيئة الخدمة: التحقق من Ollama وتحميل النموذج."""
        # التحقق من صحة Ollama
        self._health = self.check_health()

        if not self._health.is_running:
            logger.warning(
                "Ollama لا يعمل على %s — سيتم استخدام Ollama كـ Fallback فقط. "
                "شغّل: docker run -d -p 11434:11434 ollama/ollama",
                self.base_url,
            )
            self._is_available = False
            return

        self._is_available = True

        # التحقق من وجود النموذج وتحميله إذا لزم
        if self.model not in self._health.models_available:
            logger.info("النموذج '%s' غير موجود — بدء التحميل...", self.model)
            if self.pull_model(self.model):
                logger.info("تم تحميل النموذج '%s' بنجاح", self.model)
            else:
                # محاولة نموذج بديل
                for alt in FALLBACK_MODELS:
                    if alt in self._health.models_available:
                        logger.info("استخدام النموذج البديل: %s", alt)
                        self.model = alt
                        self._stats["fallback_used"] += 1
                        break
                else:
                    logger.warning("لا يوجد نموذج متاح — سيتم استخدام الردود التجريبية")
                    self._is_available = False

        # تحميل البرومبتات من GLM Client
        self._load_system_prompts()

    def _load_system_prompts(self):
        """تحميل البرومبتات من glm_client لضمان التوافق."""
        try:
            from ai.glm_client import (
                SYSTEM_PROMPT_CHAT,
                SYSTEM_PROMPT_MATCHMAKING,
                SYSTEM_PROMPT_ADVISORY,
                build_chat_prompt,
                build_matchmaking_prompt,
                build_advisory_report_prompt,
            )
            self._system_prompts = {
                "chat": SYSTEM_PROMPT_CHAT,
                "matchmaking": SYSTEM_PROMPT_MATCHMAKING,
                "advisory": SYSTEM_PROMPT_ADVISORY,
                "build_chat": build_chat_prompt,
                "build_matchmaking": build_matchmaking_prompt,
                "build_advisory": build_advisory_report_prompt,
            }
        except ImportError as e:
            logger.warning("لم يتم تحميل البرومبتات من glm_client: %s", e)
            self._system_prompts = None

    # ──────────────────────────────────────────────────────────
    # 4.1 فحص الصحة والنماذج
    # ──────────────────────────────────────────────────────────

    def check_health(self) -> OllamaHealthStatus:
        """
        فحص صحة خدمة Ollama.

        Returns:
            OllamaHealthStatus مع معلومات الحالة والنماذج المتاحة
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("models", []):
                    name = m.get("name", "")
                    size_bytes = m.get("size", 0)
                    models.append(name)

                return OllamaHealthStatus(
                    is_running=True,
                    models_available=models,
                )
        except requests.ConnectionError:
            logger.debug("Ollama غير متاح على %s", self.base_url)
        except Exception as e:
            logger.error("خطأ في فحص صحة Ollama: %s", e)

        return OllamaHealthStatus(is_running=False, error_message="غير قادر على الاتصال بـ Ollama")

    def list_models(self) -> List[OllamaModelInfo]:
        """
        استرجاع قائمة النماذج المتاحة.

        Returns:
            قائمة OllamaModelInfo
        """
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=10)
            resp.raise_for_status()
            data = resp.json()

            models = []
            for m in data.get("models", []):
                details = m.get("details", {})
                size_bytes = m.get("size", 0)
                models.append(OllamaModelInfo(
                    name=m.get("name", ""),
                    size_gb=round(size_bytes / (1024 ** 3), 2),
                    quantization=details.get("quantization_level", "unknown"),
                    family=details.get("family", "unknown"),
                    parameter_size=details.get("parameter_size", "unknown"),
                    is_available=True,
                ))
            return models

        except Exception as e:
            logger.error("خطأ في استرجاع قائمة النماذج: %s", e)
            return []

    def pull_model(self, model_name: str) -> bool:
        """
        تحميل نموذج من مستودع Ollama.

        Args:
            model_name: اسم النموذج (مثال: qwen2.5:7b)

        Returns:
            True إذا تم التحميل بنجاح
        """
        logger.info("بدء تحميل النموذج: %s ...", model_name)

        try:
            resp = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=600,  # 10 دقائق كحد أقصى للتحميل
            )
            resp.raise_for_status()
            self._stats["model_pulls"] += 1
            logger.info("تم تحميل النموذج '%s' بنجاح", model_name)
            return True

        except requests.exceptions.Timeout:
            logger.error("انتهت مهلة تحميل النموذج '%s'", model_name)
            return False
        except requests.exceptions.RequestException as e:
            logger.error("فشل تحميل النموذج '%s': %s", model_name, e)
            return False

    def delete_model(self, model_name: str) -> bool:
        """حذف نموذج من Ollama."""
        try:
            resp = requests.delete(
                f"{self.base_url}/api/delete",
                json={"name": model_name},
                timeout=30,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("فشل حذف النموذج: %s", e)
            return False

    @property
    def is_available(self) -> bool:
        """هل Ollama متاح وجاهز للاستخدام؟"""
        return self._is_available

    @property
    def stats(self) -> Dict[str, Any]:
        """إحصائيات الاستخدام."""
        return dict(self._stats)

    # ──────────────────────────────────────────────────────────
    # 4.2 دوال التدفق الرئيسية (متوافقة مع GLM Client)
    # ──────────────────────────────────────────────────────────

    def stream_chat(
        self,
        user_query: str,
        context: str,
        temperature: float = 0.4,
    ) -> Generator[str, None, None]:
        """
        محادثة عادية مع سياق الأراضي (تدفق).

        متوافق مع واجهة GLM Client.
        يُستخدم في علامة التبويب "المساعد الذكي".

        Args:
            user_query: استعلام المستثمر
            context: نص سياق الأراضي المسترجعة
            temperature: درجة الحرارة (الافتراضي: 0.4)

        Yields:
            أجزاء النص المتدفقة
        """
        if self._system_prompts and self._system_prompts.get("build_chat"):
            messages = self._system_prompts["build_chat"](user_query, context)
        else:
            messages = self._build_fallback_chat_messages(user_query, context)

        yield from self._stream_ollama(messages, temperature)

    def stream_matchmaking(
        self,
        criteria_summary: str,
        context_text: str,
        temperature: float = 0.4,
    ) -> Generator[str, None, None]:
        """
        تقرير المطابقة الاستباقية (تدفق).

        متوافق مع واجهة GLM Client.
        يُستخدم عند تفعيل "المطابقة الاستباقية".

        Args:
            criteria_summary: ملخص شروط المستثمر
            context_text: نص نتائج محرك المطابقة
            temperature: درجة الحرارة (الافتراضي: 0.4)

        Yields:
            أجزاء النص المتدفقة
        """
        if self._system_prompts and self._system_prompts.get("build_matchmaking"):
            messages = self._system_prompts["build_matchmaking"](criteria_summary, context_text)
        else:
            messages = self._build_fallback_matchmaking_messages(criteria_summary, context_text)

        yield from self._stream_ollama(messages, temperature, max_tokens=3000)

    def stream_advisory_report(
        self,
        criteria_summary: str,
        match_context: str,
        temperature: float = 0.3,
    ) -> Generator[str, None, None]:
        """
        تقرير الجدوى الاستشاري الشامل (تدفق).

        متوافق مع واجهة GLM Client.
        هذا هو الوضع الأكثر تقدماً — يُنتج تقريراً مؤسسياً كاملاً.

        Args:
            criteria_summary: ملخص شروط المستثمر
            match_context: سياق نتائج محرك المطابقة التفصيلي
            temperature: درجة الحرارة (الافتراضي: 0.3 — أقل للدقة)

        Yields:
            أجزاء النص المتدفقة
        """
        if self._system_prompts and self._system_prompts.get("build_advisory"):
            messages = self._system_prompts["build_advisory"](criteria_summary, match_context)
        else:
            messages = self._build_fallback_advisory_messages(criteria_summary, match_context)

        yield from self._stream_ollama(messages, temperature, max_tokens=4096)

    def chat_completion(
        self,
        user_query: str,
        context: str,
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> str:
        """
        محادثة عادية — رد كامل (بدون تدفق).

        مفيد عندما لا يحتاج التطبيق للتدفق.

        Returns:
            نص الرد الكامل
        """
        if self._system_prompts and self._system_prompts.get("build_chat"):
            messages = self._system_prompts["build_chat"](user_query, context)
        else:
            messages = self._build_fallback_chat_messages(user_query, context)

        return self._call_ollama(messages, temperature, max_tokens)

    # ──────────────────────────────────────────────────────────
    # 4.3 محرك الاستدعاء الداخلي
    # ──────────────────────────────────────────────────────────

    def _stream_ollama(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> Generator[str, None, None]:
        """
        استدعاء Ollama API مع التدفق.

        Args:
            messages: قائمة الرسائل (system + user)
            temperature: درجة الحرارة
            max_tokens: الحد الأقصى للرموز

        Yields:
            أجزاء النص من Ollama
        """
        self._stats["total_requests"] += 1

        if not self._is_available:
            self._stats["failed_requests"] += 1
            yield self._fallback_response()
            return

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            },
        }

        try:
            with requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=self.timeout,
            ) as resp:
                resp.raise_for_status()

                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue

                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")

                        if content:
                            self._stats["successful_requests"] += 1
                            self._stats["total_tokens_estimated"] += len(content.split())
                            yield content

                        # التحقق من انتهاء التدفق
                        if chunk.get("done", False):
                            break

                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.Timeout:
            self._stats["failed_requests"] += 1
            logger.error("انتهت مهلة استجابة Ollama (%d ثانية)", self.timeout)
            yield (
                "\n\n⚠️ انتهت مهلة استجابة النموذج المحلي. "
                "قد يكون النموذج الكبير بطيئاً على جهازك. "
                "جرب نموذجاً أصغر مثل mistral:7b أو phi3:mini.\n"
            )
        except requests.exceptions.ConnectionError:
            self._stats["failed_requests"] += 1
            self._is_available = False
            logger.error("فقد الاتصال بـ Ollama")
            yield self._fallback_response()
        except Exception as e:
            self._stats["failed_requests"] += 1
            logger.error("خطأ غير متوقع في Ollama: %s", e)
            yield f"\n\n⚠️ خطأ في النموذج المحلي: {e}\n"

    def _call_ollama(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> str:
        """
        استدعاء Ollama API — رد كامل (بدون تدفق).
        """
        self._stats["total_requests"] += 1

        if not self._is_available:
            self._stats["failed_requests"] += 1
            return self._fallback_response()

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            },
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")

            self._stats["successful_requests"] += 1
            self._stats["total_tokens_estimated"] += len(content.split())
            return content

        except Exception as e:
            self._stats["failed_requests"] += 1
            logger.error("خطأ في استدعاء Ollama: %s", e)
            return self._fallback_response()

    # ──────────────────────────────────────────────────────────
    # 4.4 برومبتات احتياطية (إذا لم يتوفر glm_client)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_fallback_chat_messages(user_query: str, context: str) -> list:
        """بناء رسائل محادثة احتياطية."""
        return [
            {
                "role": "system",
                "content": (
                    "أنت مساعد استثماري متخصص في سوق الأراضي المصري. "
                    "قدم تحليلاً مهنياً مبنياً على بيانات الأراضي المقدمة. "
                    "استخدم الجنيه المصري. اختم بإخلاء مسؤولية NUCA/GAFI."
                ),
            },
            {
                "role": "user",
                "content": f"بيانات الأراضي:\n{context}\n\nاستعلام المستثمر:\n{user_query}",
            },
        ]

    @staticmethod
    def _build_fallback_matchmaking_messages(criteria: str, context: str) -> list:
        """بناء رسائل مطابقة احتياطية."""
        return [
            {
                "role": "system",
                "content": (
                    "أنت محرك مطابقة استثمارية لسوق الأراضي المصري. "
                    "حلل النتائج المرتبة حسب نسبة التوافق وقدم توصية واضحة. "
                    "استخدم الجنيه المصري."
                ),
            },
            {
                "role": "user",
                "content": f"شروط المستثمر:\n{criteria}\n\nالنتائج المرتبة:\n{context}",
            },
        ]

    @staticmethod
    def _build_fallback_advisory_messages(criteria: str, context: str) -> list:
        """بناء رسائل تقرير استشاري احتياطية."""
        return [
            {
                "role": "system",
                "content": (
                    "أنت مستشار استثماري أول ينتج تقارير جدوى مؤسسية لسوق الأراضي المصري. "
                    "استخدم بيانات محرك المطابقة 7 أبعاد وقدم توصية قابلة للتنفيذ. "
                    "هيكل التقرير: ملخص تنفيذي، تقييم المستثمر، تحليل النتائج، "
                    "تحليل مقارن، توصية استراتيجية، إخلاء مسؤولية."
                ),
            },
            {
                "role": "user",
                "content": f"شروط المستثمر:\n{criteria}\n\nنتائج المطابقة التفصيلية:\n{context}",
            },
        ]

    @staticmethod
    def _fallback_response() -> str:
        """رد احتياطي عند فشل Ollama."""
        return (
            "⚠️ النموذج المحلي غير متاح حالياً.\n\n"
            "للتشغيل:\n"
            "1. ثبّت Ollama: curl -fsSL https://ollama.com/install.sh | sh\n"
            "2. حمّل النموذج: ollama pull qwen2.5:7b\n"
            "3. شغّل الخدمة: ollama serve\n"
            "أو عبر Docker: docker run -d -p 11434:11434 ollama/ollama && docker exec -it <container> ollama pull qwen2.5:7b\n\n"
            "---\n"
            "*إخلاء مسؤولية: تقرير مُولَّد بالذكاء الاصطناعي. تحقق من NUCA/GAFI.*"
        )

    # ──────────────────────────────────────────────────────────
    # 4.5 أدوات تشخيصية
    # ──────────────────────────────────────────────────────────

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        تقرير تشخيصي شامل لخدمة Ollama.

        مفيد لصفحة الإعدادات/الصحة في Streamlit.
        """
        health = self.check_health()
        model_info = None

        if health.is_running:
            for m in self.list_models():
                if m.name == self.model or m.name.startswith(self.model.split(":")[0]):
                    model_info = {
                        "name": m.name,
                        "size_gb": m.size_gb,
                        "quantization": m.quantization,
                        "family": m.family,
                        "parameter_size": m.parameter_size,
                    }
                    break

        return {
            "ollama_running": health.is_running,
            "ollama_url": self.base_url,
            "configured_model": self.model,
            "model_loaded": model_info is not None,
            "model_info": model_info,
            "models_available": health.models_available,
            "error_message": health.error_message,
            "stats": self.stats,
            "recommendations": self._get_recommendations(health, model_info),
        }

    def _get_recommendations(self, health: OllamaHealthStatus, model_info: Optional[Dict]) -> List[str]:
        """توصيات بناءً على الحالة الراهنة."""
        recs = []

        if not health.is_running:
            recs.append("Ollama لا يعمل. شغّله بـ: ollama serve أو docker run -d -p 11434:11434 ollama/ollama")
        elif not model_info:
            recs.append(f"النموذج '{self.model}' غير محمّل. حمّله بـ: ollama pull {self.model}")
            if health.models_available:
                recs.append(f"النماذج المتاحة حالياً: {', '.join(health.models_available[:3])}")

        if self._stats["failed_requests"] > self._stats["successful_requests"]:
            recs.append("نسبة الفشل عالية. تأكد من كفاية VRAM/RAM للنموذج المحدد.")
            recs.append("جرب نموذجاً أصغر: ollama pull mistral:7b أو ollama pull phi3:mini")

        if not recs:
            recs.append("كل شيء يعمل بشكل طبيعي.")

        return recs

    def __repr__(self) -> str:
        status = "متاح" if self._is_available else "غير متاح"
        return f"LocalLLMService(model={self.model!r}, status={status}, url={self.base_url})"