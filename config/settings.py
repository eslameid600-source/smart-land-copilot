"""Smart Land Management Copilot — Configuration Bridge."""

from api.routes.settings import (AppConfig, GLMConfig, MapConfig,
                                 MatchmakingWeights, ScoringWeights,
                                 SecurityConfig, get_settings, reset_settings)

Settings = AppConfig
settings = get_settings()

__all__ = [
    "AppConfig",
    "GLMConfig",
    "MapConfig",
    "MatchmakingWeights",
    "ScoringWeights",
    "SecurityConfig",
    "Settings",
    "settings",
    "get_settings",
    "reset_settings",
]