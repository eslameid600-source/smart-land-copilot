"""
============================================================
Smart Land Management Copilot — Configuration & Settings
============================================================
Centralized configuration using pydantic-settings with
environment variable support and validation.

Environment Variables:
  GLM_API_KEY        — API key for GLM / OpenRouter
  GLM_BASE_URL       — API base URL (default: OpenRouter)
  GLM_MODEL          — Model identifier (default: glm-5-turbo)
  GLM_MODEL_FALLBACK — Fallback model if primary fails
  LOG_LEVEL          — Logging level (DEBUG, INFO, WARNING, ERROR)
  RATE_LIMIT_RPM     — Max API requests per minute
  MAX_RETRIES        — API retry attempts
  REQUEST_TIMEOUT    — API timeout in seconds
  MOCK_MODE          — Use mock responses (true/false)
============================================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class GLMConfig:
    """Configuration for the GLM LLM service."""

    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "glm-5-turbo"
    model_fallback: str = "glm-4"
    temperature: float = 0.4
    max_tokens: int = 2048
    max_tokens_matchmaking: int = 3000
    stream: bool = True

    @classmethod
    def from_env(cls) -> "GLMConfig":
        """Load GLM configuration from environment variables."""
        return cls(
            api_key=os.environ.get("GLM_API_KEY", os.environ.get("OPENROUTER_API_KEY", "")),
            base_url=os.environ.get("GLM_BASE_URL", "https://openrouter.ai/api/v1"),
            model=os.environ.get("GLM_MODEL", "glm-5-turbo"),
            model_fallback=os.environ.get("GLM_MODEL_FALLBACK", "glm-4"),
        )


@dataclass(frozen=True)
class SecurityConfig:
    """Security and reliability configuration."""

    rate_limit_rpm: int = 30
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    retry_backoff_max: float = 10.0
    request_timeout: int = 60
    stream_timeout: int = 120
    max_input_length: int = 2000
    max_chat_history: int = 50

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        """Load security configuration from environment variables."""
        return cls(
            rate_limit_rpm=int(os.environ.get("RATE_LIMIT_RPM", "30")),
            max_retries=int(os.environ.get("MAX_RETRIES", "3")),
            request_timeout=int(os.environ.get("REQUEST_TIMEOUT", "60")),
        )


@dataclass(frozen=True)
class MapConfig:
    """Map rendering configuration."""

    default_zoom: int = 6
    default_center_lat: float = 27.0
    default_center_lon: float = 30.0
    tile_url: str = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    tile_attribution: str = (
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
        '&copy; <a href="https://carto.com/">CARTO</a>'
    )
    visual_scale: float = 1.5
    popup_max_width: int = 350
    enable_clustering: bool = True
    cluster_radius: int = 80


@dataclass(frozen=True)
class MatchmakingWeights:
    """Weight configuration for the matchmaking scoring engine."""

    usage_match: float = 30.0
    area_match: float = 20.0
    price_match: float = 20.0
    utilities_match: float = 20.0
    auction_opportunity: float = 10.0

    def validate(self) -> None:
        """Ensure weights sum to exactly 100."""
        total = (
            self.usage_match
            + self.area_match
            + self.price_match
            + self.utilities_match
            + self.auction_opportunity
        )
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Matchmaking weights must sum to 100, got {total}")


@dataclass(frozen=True)
class ScoringWeights:
    """Weight configuration for the RAG search scoring (0-100)."""

    usage: int = 40
    governorate: int = 25
    utility_per_keyword: int = 8
    utility_max_keywords: int = 3
    transport_per_keyword: int = 8
    transport_max_keywords: int = 3
    area: int = 5
    price: int = 5


@dataclass(frozen=True)
class AppConfig:
    """Root application configuration — aggregates all sub-configs."""

    app_name: str = "Smart Land Management Copilot"
    app_version: str = "3.0.0"
    debug: bool = False
    mock_mode: bool = False
    log_level: str = "INFO"
    data_dir: str = "data"

    glm: GLMConfig = field(default_factory=GLMConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    map_config: MapConfig = field(default_factory=MapConfig)
    matchmaking_weights: MatchmakingWeights = field(default_factory=MatchmakingWeights)
    scoring_weights: ScoringWeights = field(default_factory=ScoringWeights)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load complete configuration from environment."""
        mock = os.environ.get("MOCK_MODE", "false").lower() in ("true", "1", "yes")
        return cls(
            debug=os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes"),
            mock_mode=mock or not os.environ.get("GLM_API_KEY"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            glm=GLMConfig.from_env(),
            security=SecurityConfig.from_env(),
        )

    def validate(self) -> List[str]:
        """Validate configuration and return list of warnings/errors."""
        issues: List[str] = []
        if not self.glm.api_key and not self.mock_mode:
            issues.append(
                "WARNING: GLM_API_KEY not set. Running in mock/demo mode."
            )
        try:
            self.matchmaking_weights.validate()
        except ValueError as e:
            issues.append(f"ERROR: {e}")
        if self.security.rate_limit_rpm < 1:
            issues.append("ERROR: RATE_LIMIT_RPM must be >= 1")
        if self.security.max_retries < 0:
            issues.append("ERROR: MAX_RETRIES must be >= 0")
        return issues


# ----------------------------------------------------------
# Singleton instance — loaded once at startup
# ----------------------------------------------------------
_settings: Optional[AppConfig] = None


def get_settings() -> AppConfig:
    """Get or create the global settings singleton."""
    global _settings
    if _settings is None:
        _settings = AppConfig.from_env()
        issues = _settings.validate()
        for issue in issues:
            if issue.startswith("ERROR"):
                raise RuntimeError(issue)
        _settings.matchmaking_weights.validate()
    return _settings


def reset_settings() -> None:
    """Reset the settings singleton (useful for testing)."""
    global _settings
    _settings = None