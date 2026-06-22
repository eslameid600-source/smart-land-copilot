"""
============================================================
Smart Land Management Copilot — GLM Service
============================================================
Production-grade LLM client with:
  - Retry mechanism with exponential backoff
  - Model fallback (primary → fallback model)
  - Streaming and non-streaming abstraction
  - Token/cost tracking
  - Rate limiting
  - Input validation & prompt injection protection
  - Structured logging
  - Mock fallback for demo mode

Design Pattern: Strategy Pattern (stream vs non-stream),
                Decorator Pattern (retry, rate-limit)
SOLID:
  - SRP: Only LLM communication
  - OCP: New prompt modes via methods, not class changes
  - DIP: Depends on AppConfig, not hardcoded values
============================================================
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests

from config.settings import AppConfig, get_settings

logger = logging.getLogger(__name__)


# ----------------------------------------------------------
# Prompt Injection Protection
# ----------------------------------------------------------

INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"system\s*:?\s*<", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your)", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"###\s*(instruction|system|human|assistant)\s*:", re.IGNORECASE),
]


def validate_input(text: str, max_length: int = 2000) -> Tuple[bool, str]:
    """
    Validate user input for safety.

    Returns:
        (is_valid, sanitized_or_original_text)
    """
    if not text or not text.strip():
        return False, ""

    if len(text) > max_length:
        logger.warning("Input truncated from %d to %d chars", len(text), max_length)
        text = text[:max_length]

    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning("Potential prompt injection detected and neutralized")
            text = pattern.sub("[FILTERED]", text)

    return True, text


# ----------------------------------------------------------
# Token Usage Tracker
# ----------------------------------------------------------

@dataclass
class TokenUsage:
    """Track token consumption across API calls."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0
    model_name: str = ""

    def record(self, prompt: int, completion: int, model: str = "") -> None:
        """Record a single API call's token usage."""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.call_count += 1
        if model:
            self.model_name = model

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "call_count": self.call_count,
            "model": self.model_name,
        }


# ----------------------------------------------------------
# Rate Limiter (Token Bucket)
# ----------------------------------------------------------

class RateLimiter:
    """
    Simple token-bucket rate limiter.

    Tracks API call timestamps and blocks if the RPM limit
    is exceeded within the current window.
    """

    def __init__(self, max_rpm: int = 30) -> None:
        self._max_rpm = max_rpm
        self._timestamps: List[float] = []

    def acquire(self) -> float:
        """
        Attempt to acquire a rate-limit token.

        Returns the number of seconds to wait (0 if allowed).
        """
        now = time.time()
        window_start = now - 60.0

        # Prune old timestamps
        self._timestamps = [t for t in self._timestamps if t > window_start]

        if len(self._timestamps) >= self._max_rpm:
            wait_time = self._timestamps[0] + 60.0 - now + 0.1
            logger.warning("Rate limit reached. Waiting %.1fs", wait_time)
            return max(wait_time, 0.1)

        self._timestamps.append(now)
        return 0.0


# ----------------------------------------------------------
# System Prompts
# ----------------------------------------------------------

SYSTEM_PROMPT_CHAT = """\
You are the "Smart Land Management Copilot" — an expert investment \
advisory AI specializing in Egyptian land and real estate markets. \
Your role is to help investors evaluate land parcels for their \
project needs by providing data-driven, professional feasibility insights.

RULES:
1. Base your analysis ONLY on the retrieved land records provided below. \
   Do NOT fabricate data or make up land parcels that are not in the database.
2. For each recommended land, discuss: location advantages, soil suitability, \
   infrastructure readiness, pricing, and alignment with the investor's project type.
3. If no lands match the query, clearly state that and suggest what criteria \
   to relax (e.g., "Consider expanding your search to neighboring governorates").
4. Keep your tone professional, concise, and investment-focused.
5. Use EGP for all monetary values. Mention relevant Egyptian laws or \
   investment incentives when applicable (e.g., Investment Law No. 72/2017).
6. Structure your response with clear headings and bullet points for readability.
7. Always end with a disclaimer that this is an AI-generated advisory and \
   the investor should verify with the New Urban Communities Authority (NUCA) \
   or the General Authority for Investment (GAFI).
"""

SYSTEM_PROMPT_MATCHMAKING = """\
You are the "Smart Land Management Copilot" — a proactive investment \
matchmaking AI for Egyptian land markets. An investor has specified \
their exact requirements, and the system has ranked ALL available \
lands by compatibility percentage.

YOUR TASK:
1. Start by saying (in Arabic and English):
   "Based on your specified criteria, here are the best lands in Egypt \
   that match your investment requirements, ranked by compatibility."
2. For each of the TOP 3-5 lands (those with highest compatibility), \
   provide a detailed analysis covering:
   - Why this land matches the investor's criteria (strengths)
   - Any gaps or shortcomings (e.g., missing a utility, area slightly small)
   - Economic advantages (proximity to ports, highways, tax incentives)
   - If the land is an AUCTION, highlight the auction date, starting price, \
     and whether it represents good value vs. direct-sale alternatives.
3. Compare the top 2 options and make a final recommendation.
4. If auction lands appear, advise the investor on auction strategy.
5. Use EGP for all monetary values.
6. End with the standard NUCA/GAFI disclaimer.
"""


# ----------------------------------------------------------
# GLM Service
# ----------------------------------------------------------

class GLMService:
    """
    Production-grade GLM LLM service.

    Features:
    - Automatic retry with exponential backoff
    - Model fallback (primary → fallback)
    - Rate limiting
    - Streaming and non-streaming modes
    - Token usage tracking
    - Mock mode for development
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self._config = config or get_settings()
        self._rate_limiter = RateLimiter(self._config.security.rate_limit_rpm)
        self._usage = TokenUsage()
        self._session = requests.Session()

    @property
    def usage(self) -> TokenUsage:
        """Access the token usage tracker."""
        return self._usage

    @property
    def is_mock_mode(self) -> bool:
        """Check if running in mock/demo mode."""
        return self._config.mock_mode or not self._config.glm.api_key

    # ----------------------------------------------------------
    # Prompt Builders
    # ----------------------------------------------------------

    @staticmethod
    def build_chat_prompt(user_query: str, context_text: str) -> List[Dict[str, str]]:
        """Construct messages for standard chat-based RAG."""
        user_message = (
            f"Below are the land records retrieved from the Egyptian Land Database "
            f"that are most relevant to the investor's query.\n\n"
            f"--- BEGIN RETRIEVED CONTEXT ---\n{context_text}\n--- END RETRIEVED CONTEXT ---\n\n"
            f'INVESTOR QUERY:\n"{user_query}"\n\n'
            f"Please provide a professional feasibility analysis based ONLY on the above "
            f"land records. Recommend the best matches, explain why they fit, and highlight "
            f"any risks or considerations."
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT_CHAT},
            {"role": "user", "content": user_message},
        ]

    @staticmethod
    def build_matchmaking_prompt(
        criteria_summary: str,
        context_text: str,
    ) -> List[Dict[str, str]]:
        """Construct messages for the proactive matchmaking scenario."""
        user_message = (
            f"An investor has used the 'Proactive Investor Matchmaking' feature and specified "
            f"the following exact criteria:\n\n"
            f"--- INVESTOR CRITERIA ---\n{criteria_summary}\n--- END CRITERIA ---\n\n"
            f"The system has analyzed ALL lands in the database and ranked them by compatibility. "
            f"Here are the results:\n\n"
            f"--- BEGIN RANKED LAND RESULTS ---\n{context_text}\n--- END RANKED LAND RESULTS ---\n\n"
            f"Please provide a comprehensive matchmaking analysis. Focus on the "
            f"highest-compatible lands, highlight any AUCTION opportunities, "
            f"and make a clear final recommendation."
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT_MATCHMAKING},
            {"role": "user", "content": user_message},
        ]

    # ----------------------------------------------------------
    # Core API Methods
    # ----------------------------------------------------------

    def chat(
        self,
        user_query: str,
        context_text: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Non-streaming chat completion.

        Returns the full response text.
        """
        # Input validation
        is_valid, query = validate_input(user_query, self._config.security.max_input_length)
        if not is_valid:
            return "Please provide a valid query."

        if self.is_mock_mode:
            return self._mock_response(query, context_text)

        messages = self.build_chat_prompt(query, context_text)
        return self._call_api(
            messages=messages,
            temperature=temperature or self._config.glm.temperature,
            max_tokens=max_tokens or self._config.glm.max_tokens,
        )

    def stream_chat(
        self,
        user_query: str,
        context_text: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Generator[str, None, None]:
        """
        Streaming chat completion.

        Yields text chunks as they arrive from the API.
        """
        is_valid, query = validate_input(user_query, self._config.security.max_input_length)
        if not is_valid:
            yield "Please provide a valid query."
            return

        if self.is_mock_mode:
            mock = self._mock_response(query, context_text)
            yield from self._simulate_stream(mock)
            return

        messages = self.build_chat_prompt(query, context_text)
        yield from self._stream_api(
            messages=messages,
            temperature=temperature or self._config.glm.temperature,
            max_tokens=max_tokens or self._config.glm.max_tokens,
        )

    def matchmaking(
        self,
        criteria_summary: str,
        context_text: str,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Non-streaming matchmaking analysis.

        Returns the full analysis text.
        """
        is_valid, criteria = validate_input(criteria_summary, self._config.security.max_input_length)
        if not is_valid:
            return "Please provide valid criteria."

        if self.is_mock_mode:
            return self._mock_matchmaking_response(criteria, context_text)

        messages = self.build_matchmaking_prompt(criteria, context_text)
        return self._call_api(
            messages=messages,
            temperature=temperature or self._config.glm.temperature,
            max_tokens=self._config.glm.max_tokens_matchmaking,
        )

    def stream_matchmaking(
        self,
        criteria_summary: str,
        context_text: str,
        temperature: Optional[float] = None,
    ) -> Generator[str, None, None]:
        """
        Streaming matchmaking analysis.

        Yields text chunks.
        """
        is_valid, criteria = validate_input(criteria_summary, self._config.security.max_input_length)
        if not is_valid:
            yield "Please provide valid criteria."
            return

        if self.is_mock_mode:
            mock = self._mock_matchmaking_response(criteria, context_text)
            yield from self._simulate_stream(mock)
            return

        messages = self.build_matchmaking_prompt(criteria, context_text)
        yield from self._stream_api(
            messages=messages,
            temperature=temperature or self._config.glm.temperature,
            max_tokens=self._config.glm.max_tokens_matchmaking,
        )

    # ----------------------------------------------------------
    # Internal: API Communication with Retry
    # ----------------------------------------------------------

    def _call_api(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """
        Make a non-streaming API call with retry and fallback.

        Tries the primary model, then falls back to the fallback model.
        Each attempt includes exponential backoff retry.
        """
        for model in [self._config.glm.model, self._config.glm.model_fallback]:
            try:
                return self._call_with_retry(model, messages, temperature, max_tokens, stream=False)
            except GLMAPIError as e:
                logger.warning("Model %s failed: %s. Trying fallback...", model, e)
                continue

        return self._mock_response("", "API unavailable after all retries")

    def _stream_api(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Generator[str, None, None]:
        """
        Make a streaming API call with retry and fallback.

        Yields text chunks. Tries primary model, then fallback.
        """
        for model in [self._config.glm.model, self._config.glm.model_fallback]:
            try:
                yield from self._call_with_retry(
                    model, messages, temperature, max_tokens, stream=True
                )
                return
            except GLMAPIError as e:
                logger.warning("Model %s streaming failed: %s. Trying fallback...", model, e)
                continue

        mock = self._mock_response("", "API unavailable after all retries")
        yield from self._simulate_stream(mock)

    def _call_with_retry(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool = False,
    ) -> Any:
        """
        Execute an API call with exponential backoff retry.

        Returns:
          - str for non-streaming calls
          - Generator for streaming calls

        Raises:
          GLMAPIError: After all retries are exhausted.
        """
        last_error: Optional[Exception] = None
        base_backoff = self._config.security.retry_backoff_base
        max_backoff = self._config.security.retry_backoff_max
        max_retries = self._config.security.max_retries

        for attempt in range(max_retries + 1):
            # Rate limit check
            wait = self._rate_limiter.acquire()
            if wait > 0:
                time.sleep(wait)

            try:
                if stream:
                    return self._do_stream_request(model, messages, temperature, max_tokens)
                else:
                    return self._do_sync_request(model, messages, temperature, max_tokens)

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_error = e
                if attempt < max_retries:
                    backoff = min(base_backoff ** (attempt + 1), max_backoff)
                    logger.warning(
                        "API error (attempt %d/%d): %s. Retrying in %.1fs",
                        attempt + 1, max_retries + 1, e, backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error("All %d retries exhausted for model %s", max_retries + 1, model)

            except requests.exceptions.HTTPError as e:
                last_error = e
                # Don't retry 4xx errors (client errors)
                resp = getattr(e, "response", None)
                if resp and 400 <= resp.status_code < 500:
                    logger.error("Client error %d, not retrying: %s", resp.status_code, e)
                    break
                if attempt < max_retries:
                    backoff = min(base_backoff ** (attempt + 1), max_backoff)
                    logger.warning(
                        "HTTP error (attempt %d/%d): %s. Retrying in %.1fs",
                        attempt + 1, max_retries + 1, e, backoff,
                    )
                    time.sleep(backoff)

        raise GLMAPIError(f"All retries failed: {last_error}")

    def _do_sync_request(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Execute a synchronous (non-streaming) API request."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = self._build_headers()

        resp = self._session.post(
            f"{self._config.glm.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self._config.security.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        # Track usage
        usage_data = data.get("usage", {})
        self._usage.record(
            prompt=usage_data.get("prompt_tokens", 0),
            completion=usage_data.get("completion_tokens", 0),
            model=model,
        )

        logger.info(
            "GLM sync call OK: model=%s, tokens=%s",
            model, usage_data,
        )
        return data["choices"][0]["message"]["content"]

    def _do_stream_request(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Generator[str, None, None]:
        """Execute a streaming API request, yielding text chunks."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = self._build_headers()

        with self._session.post(
            f"{self._config.glm.base_url}/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=self._config.security.stream_timeout,
        ) as resp:
            resp.raise_for_status()
            prompt_tokens = 0
            completion_tokens = 0

            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        completion_tokens += 1  # Approximate
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

            self._usage.record(prompt=prompt_tokens, completion=completion_tokens, model=model)
            logger.info("GLM stream completed: model=%s", model)

    def _build_headers(self) -> Dict[str, str]:
        """Build API request headers."""
        return {
            "Authorization": f"Bearer {self._config.glm.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://smart-land-copilot.app",
            "X-Title": "Smart Land Management Copilot",
        }

    # ----------------------------------------------------------
    # Mock Responses (Demo / Fallback Mode)
    # ----------------------------------------------------------

    @staticmethod
    def _simulate_stream(text: str, chunk_size: int = 6) -> Generator[str, None, None]:
        """Split text into small chunks for simulated streaming."""
        words = text.split(" ")
        buffer = ""
        for w in words:
            buffer += w + " "
            if len(buffer) > chunk_size:
                yield buffer
                buffer = ""
        if buffer:
            yield buffer

    @staticmethod
    def _mock_response(user_query: str, context_text: str) -> str:
        """Mock response for standard chat demo mode."""
        if "No matching land records" in context_text:
            return (
                "Based on your query, no matching land records were found in the current "
                "database. I recommend broadening your search criteria — for example, "
                "considering adjacent governorates or a wider range of land-use categories. "
                "Feel free to ask with different keywords."
            )
        return (
            "## Feasibility Analysis (Demo Mode)\n\n"
            "The following recommendations are based on the retrieved land records:\n\n"
            f"{context_text}\n\n"
            "**Note:** This is a mock response generated in demo mode (no API key configured). "
            "To receive AI-powered feasibility insights, set the `GLM_API_KEY` environment "
            "variable and restart the application.\n\n---\n"
            "*Disclaimer: This is an AI-generated advisory. Always verify with the "
            "New Urban Communities Authority (NUCA) or the General Authority for "
            "Investment and Free Zones (GAFI) before making investment decisions.*"
        )

    @staticmethod
    def _mock_matchmaking_response(criteria_summary: str, context_text: str) -> str:
        """Mock response for matchmaking demo mode."""
        return (
            "## Proactive Matchmaking Report (Demo Mode)\n\n"
            f"**Your Criteria:** {criteria_summary}\n\n---\n\n"
            f"{context_text}\n\n---\n\n"
            "**Top Recommendation:** Based on the compatibility scores above, "
            "the highest-ranked land(s) best match your requirements. "
            "Review the compatibility percentage and match details for each option.\n\n"
            "**Auction Opportunities:** Check the lands marked as 'Public Auction' — "
            "they may offer better value than direct-sale options.\n\n"
            "**Note:** This is a mock response generated in demo mode (no API key configured). "
            "To receive AI-powered matchmaking analysis, set the `GLM_API_KEY` environment "
            "variable and restart the application.\n\n---\n"
            "*Disclaimer: This is an AI-generated advisory. Always verify with NUCA or GAFI.*"
        )


# ----------------------------------------------------------
# Custom Exception
# ----------------------------------------------------------

class GLMAPIError(Exception):
    """Raised when GLM API calls fail after all retries."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ----------------------------------------------------------
# Module-level singleton
# ----------------------------------------------------------

_glm_service: Optional[GLMService] = None


def get_glm_service() -> GLMService:
    """Get or create the global GLM service singleton."""
    global _glm_service
    if _glm_service is None:
        _glm_service = GLMService()
    return _glm_service


def reset_glm_service() -> None:
    """Reset the GLM service singleton (useful for testing)."""
    global _glm_service
    _glm_service = None