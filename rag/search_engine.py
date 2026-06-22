"""rag.search_engine — facade re-exporting from api.routes.search_engine.

The actual api.routes.search_engine module exposes:
    - compute_compatibility_score(land, criteria) → MatchResult
    - investor_smart_match(criteria, top_k, min_score) → List[MatchResult]
    - classify_seller(owned_land_ids, lands_data) → SellerProfile
    - classify_buyer(buyer_data) → BuyerProfile
    - classify_all_sellers / classify_all_buyers
    - format_match_results_for_llm
    - extract_intent (re-exported via RAGService)

We re-export them all, plus a small `search` alias for callers that
expect a simple `search(query, ...)` function.
"""

from typing import Any, Dict, List

from api.routes.rag_service import RAGService, get_rag_service  # noqa: F401
from api.routes.search_engine import (  # noqa: F401
    compute_compatibility_score,
    investor_smart_match,
    classify_seller,
    classify_buyer,
    classify_all_sellers,
    classify_all_buyers,
    format_match_results_for_llm,
)


def extract_intent(query: str):
    """Extract query intent via the shared RAGService singleton."""
    svc = get_rag_service()
    return svc.extract_intent(query) if hasattr(svc, "extract_intent") else None


def search(query: str, top_k: int = 10, **kwargs) -> List[Dict[str, Any]]:
    """Simple text-based search over the land catalog."""
    svc = get_rag_service()
    if hasattr(svc, "search"):
        results = svc.search(query, top_k=top_k, **kwargs)
        return [r[0] if isinstance(r, tuple) else r for r in results]

    # Fallback: naive catalog scan
    from api.routes.account_store import lands_catalog_global
    if not query:
        return list(lands_catalog_global.values())[:top_k]
    q = query.lower()
    out = []
    for land in lands_catalog_global.values():
        name = (land.get("land_name") or "").lower()
        gov = (land.get("governorate") or "").lower()
        city = (land.get("region_city") or "").lower()
        land_id = (land.get("land_id") or "").lower()
        if q in name or q in gov or q in city or q in land_id:
            out.append(land)
        if len(out) >= top_k:
            break
    return out


def build_index(lands=None):
    """No-op index builder."""
    return None


def filter_lands_by_usage(lands, usage_type: str):
    """Filter a list of land dicts by usage_type (case-insensitive)."""
    if not usage_type:
        return list(lands)
    u = usage_type.lower()
    return [
        l for l in lands
        if (l.get("usage_type") or "").lower() == u
        or (l.get("usage") or "").lower() == u
    ]


def format_context_for_llm(results, intent=None):
    """Format search results + intent into a context string for the LLM."""
    # Try the RAGService.build_context first
    try:
        svc = get_rag_service()
        if hasattr(svc, "build_context"):
            return svc.build_context(results)
    except Exception:
        pass

    # Fallback: naive formatting
    lines = []
    for r in results:
        if isinstance(r, tuple):
            land, score = r
        else:
            land, score = r, None
        name = land.get("land_name") or land.get("land_id", "")
        gov = land.get("governorate", "")
        city = land.get("region_city", "")
        price = land.get("total_price_egp", 0)
        score_str = f" (score: {score})" if score is not None else ""
        lines.append(f"- {name} | {gov}/{city} | {price:,.0f} EGP{score_str}")
    header = "نتائج البحث عن الأراضي:\n" if lines else "لا توجد نتائج."
    return header + "\n".join(lines)


__all__ = [
    "RAGService",
    "get_rag_service",
    "compute_compatibility_score",
    "investor_smart_match",
    "classify_seller",
    "classify_buyer",
    "classify_all_sellers",
    "classify_all_buyers",
    "format_match_results_for_llm",
    "extract_intent",
    "search",
    "search_lands",
    "build_index",
    "filter_lands_by_usage",
    "format_context_for_llm",
]

# Alias for callers that prefer the `search_lands` name
search_lands = search
