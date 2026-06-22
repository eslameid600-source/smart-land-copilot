"""services.glm_service — facade re-exporting GLM client functions from api.routes.glm_client.

The underlying api.routes.glm_client module exposes module-level
functions (not a GLMClient class), so this facade re-exports them
and also provides a small GLMClient wrapper class for callers
that prefer an OOP interface. Also exposes get_glm_service() for
backwards compatibility.
"""

from api.routes.glm_client import (  # noqa: F401
    build_rag_prompt,
    build_matchmaking_prompt,
    build_advisory_report_prompt,
    call_glm_api,
    stream_glm_api,
    stream_matchmaking_api,
    stream_advisory_report,
    call_advisory_report,
)


class GLMClient:
    """Thin OOP wrapper around the module-level GLM functions."""

    def call_rag(self, user_query: str, context_text: str, **kwargs):
        return call_glm_api(build_rag_prompt(user_query, context_text), **kwargs)

    def call_matchmaking(self, criteria_summary: str, context_text: str, **kwargs):
        return call_glm_api(
            build_matchmaking_prompt(criteria_summary, context_text), **kwargs
        )

    def call_advisory(self, criteria_summary: str, match_context: str, **kwargs):
        return call_advisory_report(criteria_summary, match_context, **kwargs)

    def stream_rag(self, user_query: str, context_text: str, **kwargs):
        return stream_glm_api(build_rag_prompt(user_query, context_text), **kwargs)

    def stream_matchmaking(self, criteria_summary: str, context_text: str, **kwargs):
        return stream_matchmaking_api(criteria_summary, context_text, **kwargs)

    def stream_advisory(self, criteria_summary: str, match_context: str, **kwargs):
        return stream_advisory_report(criteria_summary, match_context, **kwargs)


# Singleton accessor — returns a shared GLMClient instance
_glm_client_singleton = None


def get_glm_service():
    """Return a shared GLMClient singleton."""
    global _glm_client_singleton
    if _glm_client_singleton is None:
        _glm_client_singleton = GLMClient()
    return _glm_client_singleton


__all__ = [
    "GLMClient",
    "get_glm_service",
    "build_rag_prompt",
    "build_matchmaking_prompt",
    "build_advisory_report_prompt",
    "call_glm_api",
    "stream_glm_api",
    "stream_matchmaking_api",
    "stream_advisory_report",
    "call_advisory_report",
]
