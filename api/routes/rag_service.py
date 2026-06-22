"""
============================================================
Smart Land Management Copilot — RAG Service
============================================================
Retrieval-Augmented Generation search service.

Features:
  - Intent extraction from natural language queries
  - Hybrid scoring (keyword + criteria matching)
  - Query expansion with synonyms/aliases
  - Re-ranking support
  - Context formatting for LLM injection
  - Caching of frequent queries

Design Pattern: Strategy (scoring), Template Method (search pipeline)
SOLID:
  - SRP: Search and retrieval logic only
  - OCP: New scoring strategies via weights config
  - DIP: Depends on repository, not raw data
============================================================
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from data.repository import LandRepository, get_repository

from config.settings import AppConfig, ScoringWeights, get_settings

logger = logging.getLogger(__name__)

@dataclass
class QueryIntent:
    """Structured representation of a parsed user query."""
    raw_query: str
    target_usage: Optional[str] = None
    target_gov: Optional[str] = None
    utility_keywords: List[str] = field(default_factory=list)
    transport_keywords: List[str] = field(default_factory=list)
    min_area: Optional[int] = None
    max_price: Optional[int] = None

    @property
    def has_filters(self) -> bool:
        """Check if the intent has any active filters."""
        return bool(self.target_usage or self.target_gov or self.utility_keywords or self.transport_keywords or self.min_area or self.max_price)
USAGE_ALIASES: Dict[str, str] = {'industrial': 'Industrial', 'factory': 'Industrial', 'factories': 'Industrial', 'manufacturing': 'Industrial', 'plant': 'Industrial', 'logistics': 'Logistics', 'warehouse': 'Logistics', 'warehousing': 'Logistics', 'storage': 'Logistics', 'distribution': 'Logistics', 'freight': 'Logistics', 'agricultural': 'Agricultural', 'farming': 'Agricultural', 'agriculture': 'Agricultural', 'crops': 'Agricultural', 'irrigation': 'Agricultural', 'residential': 'Residential', 'housing': 'Residential', 'compound': 'Residential', 'apartments': 'Residential', 'living': 'Residential'}
GOVERNORATE_ALIASES: Dict[str, str] = {'cairo': 'Cairo', 'new cairo': 'Cairo', 'new administrative capital': 'Cairo', 'sharqia': 'Sharqia', '10th of ramadan': 'Sharqia', 'tenth of ramadan': 'Sharqia', 'monufia': 'Monufia', 'sadat': 'Monufia', 'sadat city': 'Monufia', 'alexandria': 'Alexandria', 'borg el arab': 'Alexandria', 'suez': 'Suez', 'sokhna': 'Suez', 'damietta': 'Damietta', 'ismailia': 'Ismailia', 'aswan': 'Aswan', 'toshka': 'Aswan', 'beheira': 'Beheira', 'wadi el natrun': 'Beheira'}
UTILITY_KEYWORDS: List[str] = ['water', 'electricity', 'gas', 'fiber', 'fiber-optic', 'optic', 'solar', 'grid', 'pipeline', 'sewage']
TRANSPORT_KEYWORDS: List[str] = ['highway', 'road', 'port', 'airport', 'canal', 'tunnel', 'desert road', 'ring road', 'corridor']

class RAGService:
    """
    Retrieval-Augmented Generation search service.

    Pipeline: Query → Intent Extraction → Scoring → Ranking → Context Format
    """

    def __init__(self, config: Optional[AppConfig]=None, repository: Optional[LandRepository]=None) -> None:
        self._config = config or get_settings()
        self._repo = repository or get_repository()
        self._weights = self._config.scoring_weights
        self._cache: Dict[str, Tuple[List[Tuple[Dict[str, Any], int]], str]] = {}

    def search(self, query: str, top_k: int=5, min_score: int=0) -> List[Tuple[Dict[str, Any], int]]:
        """
        Main search entry point.

        Args:
            query: Natural language search query
            top_k: Maximum number of results to return
            min_score: Minimum score threshold (0-100)

        Returns:
            List of (land_dict, score) tuples, sorted by score desc.
        """
        cache_key = f'{query}:{top_k}:{min_score}'
        if cache_key in self._cache:
            logger.debug('RAG cache hit for: %s', query[:50])
            return self._cache[cache_key][0]
        intent = self.extract_intent(query)
        lands = self._repo.get_all_dicts()
        scored = self._score_all(lands, intent, min_score)
        results = scored[:top_k]
        self._cache[cache_key] = (results, intent.raw_query)
        if len(self._cache) > 100:
            oldest = list(self._cache.keys())[:20]
            for k in oldest:
                del self._cache[k]
        logger.info("RAG search: query='%s', intent=%s, results=%d", query[:60], {'usage': intent.target_usage, 'gov': intent.target_gov, 'min_area': intent.min_area, 'max_price': intent.max_price}, len(results))
        return results

    def extract_intent(self, query: str) -> QueryIntent:
        """
        Parse a natural-language query into a structured intent.

        Extracts: target usage, governorate, utility keywords,
        transport keywords, minimum area, maximum price.
        """
        normed = self._normalize(query)
        intent = QueryIntent(raw_query=query)
        for alias in sorted(USAGE_ALIASES.keys(), key=len, reverse=True):
            if alias in normed:
                intent.target_usage = USAGE_ALIASES[alias]
                break
        for alias in sorted(GOVERNORATE_ALIASES.keys(), key=len, reverse=True):
            if alias in normed:
                intent.target_gov = GOVERNORATE_ALIASES[alias]
                break
        intent.utility_keywords = [kw for kw in UTILITY_KEYWORDS if kw in normed]
        intent.transport_keywords = [kw for kw in TRANSPORT_KEYWORDS if kw in normed]
        area_match = re.search('(?:at least|minimum|min|more than|over|above)\\s*([\\d_]+)\\s*(?:sqm|sq m|square meters?|m2)?', normed)
        if area_match:
            intent.min_area = int(area_match.group(1).replace('_', ''))
        price_match = re.search('(?:under|below|max|budget|cheaper than|up to)\\s*(?:egp\\s*)?([\\d_]+)\\s*(?:egp|per\\s*sqm)?', normed)
        if price_match:
            intent.max_price = int(price_match.group(1).replace('_', ''))
        return intent

    def rerank(self, results: List[Tuple[Dict[str, Any], int]], query: str) -> List[Tuple[Dict[str, Any], int]]:
        """
        Re-rank results using query expansion.

        Adds synonym/alias-based bonus scoring to refine initial results.
        """
        if not results:
            return results
        intent = self.extract_intent(query)
        reranked = []
        for land_dict, base_score in results:
            boost = 0.0
            if intent.target_gov:
                region_lower = land_dict.get('Region_City', '').lower()
                gov_lower = intent.target_gov.lower()
                if gov_lower in region_lower:
                    boost += 5
            if intent.target_usage == 'Agricultural':
                soil = land_dict.get('Soil_Mineral_Type', '').lower()
                agri_terms = ['fertile', 'loam', 'alluvial', 'clay', 'nile']
                for term in agri_terms:
                    if term in soil:
                        boost += 2
                        break
            notes = land_dict.get('Gov_Feasibility_Notes', '').lower()
            for kw in intent.transport_keywords[:2]:
                if kw in notes:
                    boost += 2
            reranked.append((land_dict, min(base_score + int(boost), 100)))
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked

    def build_context(self, results: List[Tuple[Dict[str, Any], int]]) -> str:
        """
        Format search results into a structured text block for LLM injection.

        Accepts both:
          - List of (land_dict, score) tuples
          - List of dicts with Compatibility_Percent
        """
        if not results:
            return 'No matching land records found in the database.'
        lines = ['RETRIEVED LAND RECORDS (Egypt Land Database)', '=' * 60]
        for item in results:
            if isinstance(item, tuple):
                land, score = item
                score_label = f'{score}/100'
                compat = None
            else:
                land = item
                score_label = 'N/A'
                compat = land.get('Compatibility_Percent')
            auction_info = ''
            if land.get('Investment_Status') == 'Public Auction':
                auction_info = f"\n  Investment     : PUBLIC AUCTION\n  Auction Date   : {land.get('Auction_Date', 'N/A')}\n  Starting Price : {land.get('Starting_Price_Per_Sqm_EGP', 'N/A'):,} EGP/m2"
            else:
                auction_info = '\n  Investment     : Direct Sale'
            compat_line = ''
            if compat is not None:
                compat_line = f'\n  Compatibility  : {compat}%'
            lines.append(f"\n[Land: {land['Land_ID']}]  Score: {score_label}{compat_line}\n  Location       : {land['Governorate']} - {land['Region_City']}\n  Coordinates    : {land['Latitude']}, {land['Longitude']}\n  Area           : {land['Total_Area_Sqm']:,} sqm\n  Price/sqm      : {land['Price_Per_Sqm_EGP']:,} EGP\n  Soil/Mineral   : {land['Soil_Mineral_Type']}\n  Allowed Usage  : {land['Allowed_Usage']}\n  Highways       : {land['Nearest_Highways']}\n  Utilities      : {land['Utilities_Availability']}{auction_info}\n  Gov Notes      : {land['Gov_Feasibility_Notes']}\n")
        return '\n'.join(lines)

    def clear_cache(self) -> None:
        """Clear the search result cache."""
        self._cache.clear()

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase + strip punctuation for matching."""
        return re.sub('[^\\w\\s]', '', text.lower()).strip()

    def _score_all(self, lands: List[Dict[str, Any]], intent: QueryIntent, min_score: int) -> List[Tuple[Dict[str, Any], int]]:
        """Score all lands against the intent and return sorted results."""
        w = self._weights
        scored: List[Tuple[Dict[str, Any], int]] = []
        for land in lands:
            s = self._compute_score(land, intent, w)
            if s >= min_score:
                scored.append((land, s))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    @staticmethod
    def _compute_score(land: Dict[str, Any], intent: QueryIntent, w: ScoringWeights) -> int:
        """
        Compute a relevance score (0-100) for a single land.

        Scoring rules (configurable via ScoringWeights):
          - Exact usage match            -> w.usage
          - Governorate match            -> w.governorate (or w.governorate*0.6 for partial)
          - Each utility keyword hit     -> w.utility_per_keyword (max 3)
          - Each transport keyword hit   -> w.transport_per_keyword (max 3)
          - Area requirement satisfied   -> w.area
          - Price budget satisfied       -> w.price
        """
        score = 0
        if intent.target_usage and land['Allowed_Usage'] == intent.target_usage:
            score += w.usage
        if intent.target_gov and land['Governorate'] == intent.target_gov:
            score += w.governorate
        elif intent.target_gov:
            region_lower = land['Region_City'].lower()
            gov_lower = intent.target_gov.lower()
            if gov_lower in region_lower:
                score += int(w.governorate * 0.6)
        land_utils = land['Utilities_Availability'].lower()
        for kw in intent.utility_keywords[:w.utility_max_keywords]:
            if kw in land_utils:
                score += w.utility_per_keyword
        land_transport = (land['Nearest_Highways'] + ' ' + land['Region_City']).lower()
        for kw in intent.transport_keywords[:w.transport_max_keywords]:
            if kw in land_transport:
                score += w.transport_per_keyword
        if intent.min_area and land['Total_Area_Sqm'] >= intent.min_area:
            score += w.area
        if intent.max_price and land['Price_Per_Sqm_EGP'] <= intent.max_price:
            score += w.price
        return min(score, 100)
_rag_service: Optional[RAGService] = None

def get_rag_service() -> RAGService:
    """Get or create the global RAG service singleton."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service

def reset_rag_service() -> None:
    """Reset the RAG service singleton (useful for testing)."""
    global _rag_service
    _rag_service = None