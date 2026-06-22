"""services.rag_service — facade re-exporting RAGService from api.routes.rag_service."""

from api.routes.rag_service import (  # noqa: F401
    RAGService,
    QueryIntent,
    get_rag_service,
    reset_rag_service,
)


def search_lands(query: str, **kwargs):
    """Convenience helper: search lands via the shared RAGService singleton."""
    svc = get_rag_service()
    return svc.search(query, **kwargs) if hasattr(svc, "search") else []


def build_index(lands):
    """Convenience helper: build a RAG index from a list of lands."""
    svc = get_rag_service()
    if hasattr(svc, "build_index"):
        return svc.build_index(lands)
    return None


def proactive_match(investor_profile=None, lands=None, **kwargs):
    """Convenience helper: proactively match an investor to available lands.

    Stub implementation — returns the lands unchanged. Real implementation
    should call the matchmaking service.
    """
    if lands is None:
        lands = search_lands("", top_k=20)
    return lands


__all__ = [
    "RAGService",
    "QueryIntent",
    "get_rag_service",
    "reset_rag_service",
    "search_lands",
    "build_index",
    "proactive_match",
]
