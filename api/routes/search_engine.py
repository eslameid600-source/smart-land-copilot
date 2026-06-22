"""
Smart Land Management Copilot — RAG Search Engine v5.0 (Matchmaking Engine)
=============================================================================
Enhanced search with:
  1. Legacy RAG functions (re-exported from services/rag_service.py)
  2. NEW: Advanced Compatibility_Score Matchmaking Engine (0-100%)
  3. NEW: Tripartite Classification (Seller Volume/Value, Buyer Category)
  4. NEW: Quality-Rating-aware scoring integration
"""
from typing import Dict, List, Optional, Tuple

from data.land_database import get_all_lands
from models.matchmaking import (
    BuyerProfile,
    InvestorCriteria,
    MatchResult,
    SellerProfile,
)

from services.rag_service import proactive_match as _legacy_proactive_match

proactive_match = _legacy_proactive_match
_QUALITY_WEIGHT = {'AAA': 1.0, 'AA': 0.85, 'A': 0.65, 'B': 0.4}
_QUALITY_ORDER = {'AAA': 4, 'AA': 3, 'A': 2, 'B': 1}

def _count_matched_utilities(land: Dict, required: List[str]) -> Tuple[int, List[str]]:
    """Count how many required utilities are available. Returns (matched, missing)."""
    avail = land.get('Utilities_Availability', '').lower()
    matched = [u for u in required if u.lower() in avail]
    missing = [u for u in required if u.lower() not in avail]
    return (len(matched), missing)

def compute_compatibility_score(land: Dict, criteria: InvestorCriteria) -> MatchResult:
    """
    Compute a granular Compatibility_Score (0-100%) between a land
    record and an investor's criteria.

    Scoring dimensions (weighted):
      - Usage Match         : 0-25 pts
      - Area Adequacy       : 0-20 pts
      - Price Affordability : 0-20 pts
      - Utility Coverage    : 0-15 pts
      - Land Quality Rating : 0-10 pts
      - Auction Bonus       : 0-5 pts
      - Governorate Bonus   : 0-5 pts
    """
    scores: Dict[str, float] = {}
    reasons: List[str] = []
    warnings: List[str] = []
    total = 0.0
    if criteria.target_usage:
        if land['Allowed_Usage'] == criteria.target_usage:
            scores['usage'] = 25.0
            reasons.append(f'Exact usage match: {criteria.target_usage}')
        else:
            scores['usage'] = 0.0
            warnings.append(f"Wrong usage ({land['Allowed_Usage']} != {criteria.target_usage})")
    else:
        scores['usage'] = 25.0
        reasons.append('No usage preference specified')
    total += scores['usage']
    if criteria.min_area_sqm:
        actual = land['Total_Area_Sqm']
        if actual >= criteria.min_area_sqm:
            scores['area'] = 20.0
            reasons.append(f'Area adequate: {actual:,} sqm (need {criteria.min_area_sqm:,})')
        else:
            ratio = actual / criteria.min_area_sqm
            scores['area'] = round(ratio * 20.0, 2)
            warnings.append(f'Area undersized: {actual:,} < {criteria.min_area_sqm:,} sqm')
        scores['area_ratio'] = actual / criteria.min_area_sqm if criteria.min_area_sqm else 1.0
    else:
        scores['area'] = 20.0
        reasons.append('No area preference specified')
        scores['area_ratio'] = 1.0
    total += scores['area']
    if criteria.max_price_per_sqm:
        actual_pps = land['Price_Per_Sqm_EGP']
        if actual_pps <= criteria.max_price_per_sqm:
            scores['price'] = 20.0
            reasons.append(f'Price within budget: {actual_pps:,} EGP/sqm')
        else:
            ratio = criteria.max_price_per_sqm / actual_pps
            scores['price'] = round(min(ratio, 1.0) * 20.0, 2)
            warnings.append(f'Price over budget: {actual_pps:,} > {criteria.max_price_per_sqm:,} EGP/sqm')
        scores['price_ratio'] = criteria.max_price_per_sqm / actual_pps
    else:
        scores['price'] = 20.0
        reasons.append('No price preference specified')
        scores['price_ratio'] = 1.0
    total += scores['price']
    if criteria.required_utilities:
        matched_count, missing_utils = _count_matched_utilities(land, criteria.required_utilities)
        util_pct = matched_count / len(criteria.required_utilities)
        scores['utilities'] = round(util_pct * 15.0, 2)
        scores['util_pct'] = round(util_pct * 100, 1)
        if matched_count == len(criteria.required_utilities):
            reasons.append(f'All {matched_count} required utilities available')
        else:
            reasons.append(f'{matched_count}/{len(criteria.required_utilities)} utilities matched')
            warnings.append(f"Missing utilities: {', '.join(missing_utils)}")
    else:
        scores['utilities'] = 15.0
        scores['util_pct'] = 100.0
        reasons.append('No utility preference specified')
    total += scores['utilities']
    quality = land.get('Land_Quality_Rating', 'B')
    quality_weight = _QUALITY_WEIGHT.get(quality, 0.4)
    scores['quality'] = round(quality_weight * 10.0, 2)
    if quality == 'AAA':
        reasons.append('Prime AAA quality rating')
    elif quality == 'AA':
        reasons.append('High AA quality rating')
    elif quality == 'A':
        reasons.append('Standard A quality rating')
    else:
        warnings.append('Basic B quality rating')
    total += scores['quality']
    is_auction = land.get('Investment_Status') == 'Public Auction'
    if is_auction:
        if criteria.prefer_auction:
            scores['auction'] = 5.0
            reasons.append(f"Auction preferred match: {land.get('Auction_Date', 'TBD')}")
        else:
            scores['auction'] = 3.0
            reasons.append(f"Public auction available: {land.get('Auction_Date', 'TBD')}")
    else:
        scores['auction'] = 2.5
    total += scores['auction']
    if criteria.preferred_governorate:
        if land['Governorate'] == criteria.preferred_governorate:
            scores['governorate'] = 5.0
            reasons.append(f'Preferred governorate: {criteria.preferred_governorate}')
        else:
            scores['governorate'] = 0.0
            warnings.append(f"Wrong governorate ({land['Governorate']} != {criteria.preferred_governorate})")
    else:
        scores['governorate'] = 5.0
    total += scores['governorate']
    compatibility = min(round(total, 1), 100.0)
    return MatchResult(land_id=land['Land_ID'], compatibility_pct=compatibility, score_details=scores, match_reasons=reasons, gap_warnings=warnings, is_auction=is_auction, auction_date=land.get('Auction_Date'), starting_price_per_sqm=land.get('Starting_Price_Per_Sqm_EGP'), land_quality_rating=quality, price_affordability_ratio=scores.get('price_ratio', 1.0), area_adequacy_ratio=scores.get('area_ratio', 1.0), utility_coverage_pct=scores.get('util_pct', 100.0))

def investor_smart_match(criteria: InvestorCriteria, top_k: int=10, min_score: float=0.0) -> List[MatchResult]:
    """
    Score ALL lands against structured investor criteria.
    Returns ranked MatchResult list by Compatibility_Score (desc).

    This is the core matchmaking function used by the
    "Investor Smart Match" dashboard tab.
    """
    lands = get_all_lands()
    results: List[MatchResult] = []
    for land in lands:
        if criteria.min_quality_rating:
            land_quality = land.get('Land_Quality_Rating', 'B')
            min_order = _QUALITY_ORDER.get(criteria.min_quality_rating, 0)
            land_order = _QUALITY_ORDER.get(land_quality, 0)
            if land_order < min_order:
                continue
        match = compute_compatibility_score(land, criteria)
        if match.compatibility_pct >= min_score:
            results.append(match)
    results.sort(key=lambda m: m.compatibility_pct, reverse=True)
    return results[:top_k]

def classify_seller(owned_land_ids: List[str], lands_data: Optional[List[Dict]]=None) -> SellerProfile:
    """
    Classify a seller by both Asset Volume and Total Value.

    Volume Tiers:  Single / Small (2-5) / Medium (6-15) / Large (16-50) / Institutional (50+)
    Value Tiers:   Boutique (<50M) / Standard (50M-500M) / Premium (500M-2B) / Institutional (2B+)
    """
    if lands_data is None:
        lands_data = get_all_lands()
    land_map = {land_item['Land_ID']: land_item for land_item in lands_data}
    total_value = 0.0
    valid_ids = []
    for lid in owned_land_ids:
        land = land_map.get(lid)
        if land:
            total_value += land.get('Total_Price_EGP', 0)
            valid_ids.append(lid)
    profile = SellerProfile(seller_id='', owned_land_ids=valid_ids, total_asset_count=len(valid_ids), total_listed_value_egp=total_value)
    profile.classify()
    return profile

def classify_all_sellers(user_accounts: List[Dict], lands_data: Optional[List[Dict]]=None) -> List[Dict]:
    """
    Classify all sellers from user account data.
    Returns list of dicts with classification results.
    """
    if lands_data is None:
        lands_data = get_all_lands()
    results = []
    for account in user_accounts:
        role = account.get('role', '')
        if role not in ('Seller/Owner', 'Seller'):
            continue
        owned = account.get('owned_land_ids', [])
        profile = classify_seller(owned, lands_data)
        profile.seller_id = account.get('user_id', '')
        profile.company_name = account.get('company_name', '')
        results.append({'seller_id': profile.seller_id, 'company_name': profile.company_name, 'asset_count': profile.total_asset_count, 'total_value_egp': profile.total_listed_value_egp, 'volume_tier': profile.volume_tier.value, 'value_tier': profile.value_tier.value, 'combined_label': profile.combined_label})
    return results

def classify_buyer(buyer_data: Dict) -> BuyerProfile:
    """
    Classify a buyer/investor into:
      - Strategic Developer (ranked by scale/value of projects managed and executed)
      - Financial Buyer (ranked by land acquisition value)
    """
    profile = BuyerProfile(buyer_id=buyer_data.get('user_id', ''), company_name=buyer_data.get('company_name', ''), total_projects_executed=buyer_data.get('total_projects_executed', 0), largest_project_value_egp=buyer_data.get('largest_project_value_egp', 0), total_acquisition_value_egp=buyer_data.get('total_acquisition_value_egp', 0))
    profile.classify()
    return profile

def classify_all_buyers(user_accounts: List[Dict]) -> List[Dict]:
    """Classify all buyers from user account data."""
    results = []
    for account in user_accounts:
        role = account.get('role', '')
        if role not in ('Buyer/Investor', 'Buyer'):
            continue
        profile = classify_buyer(account)
        results.append({'buyer_id': profile.buyer_id, 'company_name': profile.company_name, 'category': profile.buyer_category.value, 'scale_label': profile.scale_label, 'projects_executed': profile.total_projects_executed, 'largest_project_egp': profile.largest_project_value_egp, 'total_acquisition_egp': profile.total_acquisition_value_egp})
    return results

def format_match_results_for_llm(matches: List[MatchResult], lands_data: Optional[List[Dict]]=None) -> str:
    """
    Convert MatchResult list into structured text for GLM-5 Turbo injection.
    Includes quality rating, auction status, and per-dimension scores.
    """
    if not matches:
        return 'No matching land records found in the database.'
    if lands_data is None:
        lands_data = get_all_lands()
    land_map = {land_item['Land_ID']: land_item for land_item in lands_data}
    lines = ['MATCHED LAND RECORDS (Investment Rating & Matchmaking System)\n' + '=' * 70, '']
    for i, match in enumerate(matches, 1):
        land = land_map.get(match.land_id, {})
        auction_info = ''
        if match.is_auction:
            auction_info = f"\n  Investment     : PUBLIC AUCTION\n  Auction Date   : {match.auction_date or 'TBD'}\n  Starting Price : {match.starting_price_per_sqm:,.0f} EGP/m²"
        else:
            auction_info = '\n  Investment     : Direct Sale'
        sd = match.score_details
        score_breakdown = f"  Score Breakdown:\n    Usage Match      : {sd.get('usage', 0):.1f}/25\n    Area Adequacy    : {sd.get('area', 0):.1f}/20\n    Price Fit        : {sd.get('price', 0):.1f}/20\n    Utility Coverage : {sd.get('utilities', 0):.1f}/15 ({match.utility_coverage_pct:.0f}%)\n    Quality Rating   : {sd.get('quality', 0):.1f}/10 ({match.land_quality_rating})\n    Auction/Location : {sd.get('auction', 0):.1f}/5 + {sd.get('governorate', 0):.1f}/5"
        lines.append(f"--- Match #{i} | Compatibility: {match.compatibility_pct:.1f}% | Quality: {match.land_quality_rating} ---\n  Land ID        : {match.land_id}\n  Location       : {land.get('Governorate', 'N/A')} - {land.get('Region_City', 'N/A')}\n  Area           : {land.get('Total_Area_Sqm', 0):,} sqm\n  Price/sqm      : {land.get('Price_Per_Sqm_EGP', 0):,} EGP\n  Total Price    : {land.get('Total_Price_EGP', 0):,.0f} EGP\n  Allowed Usage  : {land.get('Allowed_Usage', 'N/A')}\n  Utilities      : {land.get('Utilities_Availability', 'N/A')}\n  Highways       : {land.get('Nearest_Highways', 'N/A')}{auction_info}\n\n{score_breakdown}\n\n  Strengths: {'; '.join(match.match_reasons)}\n  Warnings : {('; '.join(match.gap_warnings) if match.gap_warnings else 'None')}\n  Gov Notes: {land.get('Gov_Feasibility_Notes', 'N/A')}\n")
    return '\n'.join(lines)