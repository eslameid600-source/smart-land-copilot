"""
Smart Land Management Copilot — Service Density & Clustering Service
======================================================================
Analyzes the density of existing commercial, civic, and industrial
clusters around each land parcel. Produces saturation levels, gap
reports, and formatting logic for LLM context injection.
"""
from typing import Dict, List, Optional, Tuple
from models.models.models.land import ServiceDensityData, RadiusProfile, SaturationLevel
_SATURATION_THRESHOLDS: Dict[str, Tuple[int, int, int]] = {'retail': (3, 7, 12), 'civic': (2, 5, 8), 'industrial': (3, 8, 15)}
_GAP_RECOMMENDATIONS: Dict[str, List[Dict]] = {'Retail & Entertainment': [{'usage': 'Hospital / Medical Center', 'rationale': 'Low civic density creates healthcare demand'}, {'usage': 'School / University Campus', 'rationale': 'Residential population needs education facilities'}, {'usage': 'Logistics Hub', 'rationale': 'Industrial gap supports supply-chain demand'}, {'usage': 'Residential Compound', 'rationale': 'Population density justifies housing projects'}], 'Civic Infrastructure': [{'usage': 'Shopping Mall / Retail Complex', 'rationale': 'Underserved retail market for existing population'}, {'usage': 'Entertainment / Amusement Park', 'rationale': 'No entertainment venues in proximity'}, {'usage': 'Medical Facility', 'rationale': 'Healthcare gap in the area'}, {'usage': 'Industrial Zone', 'rationale': 'No industrial competition, first-mover advantage'}], 'Industrial Infrastructure': [{'usage': 'Residential Compound', 'rationale': 'No industrial proximity — clean environment for housing'}, {'usage': 'School / University', 'rationale': 'Quiet zone suitable for educational campus'}, {'usage': 'Hospital / Medical Center', 'rationale': 'Clean air and low pollution support healthcare facilities'}, {'usage': 'Retail & Entertainment', 'rationale': 'Unsaturated retail market for worker/resident population'}]}

class DensityService:
    """
    Computes and analyzes the Service Density & Clustering Factor.

    For each land parcel, this service evaluates the concentration
    of retail/civic/industrial establishments within 2km, 5km, and
    10km radius bands. It produces:
      - Per-radius density profiles
      - Category-wise saturation levels
      - Market gap identification with actionable recommendations
      - A clustering verdict for investor decision-making
    """

    def __init__(self, primary_radius_km: float=5.0):
        self.primary_radius_km = primary_radius_km

    def analyze(self, land: Dict) -> ServiceDensityData:
        """
        Run the full density analysis on a land record.

        Expects the land dict to contain nested density cluster data
        under the key 'Service_Density_Clusters' (a list of dicts
        with radius_km, retail, civic, industrial counts).
        """
        raw_profiles = land.get('Service_Density_Clusters', [])
        profiles = self._build_profiles(raw_profiles)
        retail_sat, civic_sat, industrial_sat = self._classify_saturation(profiles)
        overall_score = self._compute_overall_score(profiles)
        gap_analysis = self._identify_gaps(retail_sat, civic_sat, industrial_sat, land)
        verdict = self._generate_verdict(overall_score, retail_sat, civic_sat, industrial_sat, land)
        return ServiceDensityData(profiles=profiles, retail_entertainment_saturation=retail_sat, civic_infrastructure_saturation=civic_sat, industrial_infrastructure_saturation=industrial_sat, overall_density_score=overall_score, market_gap_analysis=gap_analysis, clustering_verdict=verdict)

    def analyze_all(self, lands: List[Dict]) -> Dict[str, ServiceDensityData]:
        """Run density analysis on all land records. Returns dict keyed by Land_ID."""
        results = {}
        for land in lands:
            results[land['Land_ID']] = self.analyze(land)
        return results

    def generate_saturation_report(self, land: Dict) -> str:
        """
        Produce a formatted 'Market Saturation & Gap Report' string
        for direct injection into LLM system prompts or chat context.
        """
        analysis = self.analyze(land)
        land_id = land['Land_ID']
        region = f"{land['Governorate']} - {land['Region_City']}"
        usage = land['Allowed_Usage']
        lines = [f'MARKET SATURATION & GAP REPORT — {land_id} ({region})', '=' * 55, f'Land Usage Type: {usage}', '', 'DENSITY PROFILE (by radius):']
        for p in analysis.profiles:
            lines.append(f'  Within {p.radius_km:.0f}km: Retail/Entertainment: {p.retail_entertainment} | Civic Infrastructure: {p.civic_infrastructure} | Industrial: {p.industrial_infrastructure} | Total: {p.total}')
        lines.extend(['', 'SATURATION ASSESSMENT (based on {0:.0f}km radius):'.format(self.primary_radius_km), f'  Retail & Entertainment: {analysis.retail_entertainment_saturation.value}', f'  Civic Infrastructure:    {analysis.civic_infrastructure_saturation.value}', f'  Industrial:              {analysis.industrial_infrastructure_saturation.value}', f'  Overall Density Score:   {analysis.overall_density_score:.1f}/100', '', 'CLUSTERING VERDICT:', f'  {analysis.clustering_verdict}'])
        if analysis.market_gap_analysis:
            lines.extend(['', 'MARKET GAP ANALYSIS & RECOMMENDATIONS:'])
            for i, gap in enumerate(analysis.market_gap_analysis, 1):
                lines.append(f"  {i}. Recommended Alternative: {gap['recommended_usage']}")
                lines.append(f"     Rationale: {gap['rationale']}")
                if gap.get('current_usage_viable'):
                    lines.append(f"     Note: {gap['current_usage_viable']}")
        if analysis.retail_entertainment_saturation in (SaturationLevel.HIGH, SaturationLevel.CRITICAL):
            lines.extend(['', 'SATURATION WARNING:', f'  This area shows {analysis.retail_entertainment_saturation.value} retail/entertainment saturation. Investing in another mall, plaza, or similar retail venue carries elevated competition risk. Strongly consider the alternative usages identified above, or target a niche retail segment (e.g., medical mall, edu-tainment center) to differentiate from existing supply.'])
        if analysis.civic_infrastructure_saturation in (SaturationLevel.HIGH, SaturationLevel.CRITICAL):
            lines.extend(['', 'CIVIC SATURATION NOTICE:', f'  Civic infrastructure is {analysis.civic_infrastructure_saturation.value} in this area. Additional hospitals, schools, or universities may face enrollment/admission challenges. Evaluate demographic growth projections before committing to civic-type development.'])
        if analysis.industrial_infrastructure_saturation in (SaturationLevel.HIGH, SaturationLevel.CRITICAL):
            lines.extend(['', 'INDUSTRIAL SATURATION NOTICE:', f'  Industrial density is {analysis.industrial_infrastructure_saturation.value}. New factories or warehouses may compete for labor and logistics capacity. Consider specialized industrial segments or alternative sectors listed above.'])
        return '\n'.join(lines)

    def format_density_for_llm(self, land: Dict) -> str:
        """
        Compact density summary for appending to LLM context.
        Designed to be called by format_context_for_llm() in rag_service.
        """
        analysis = self.analyze(land)
        primary = self._get_primary_profile(analysis.profiles)
        if primary is None:
            return ''
        parts = [f'  Service Density ({self.primary_radius_km:.0f}km): Retail={primary.retail_entertainment} | Civic={primary.civic_infrastructure} | Industrial={primary.industrial_infrastructure} | Score={analysis.overall_density_score:.0f}/100', f'  Saturation: Retail={analysis.retail_entertainment_saturation.value}, Civic={analysis.civic_infrastructure_saturation.value}, Industrial={analysis.industrial_infrastructure_saturation.value}']
        if analysis.market_gap_analysis:
            top_gap = analysis.market_gap_analysis[0]
            parts.append(f"  Top Gap Opportunity: {top_gap['recommended_usage']} ({top_gap['rationale']})")
        parts.append(f'  Clustering: {analysis.clustering_verdict}')
        return '\n'.join(parts)

    @staticmethod
    def _build_profiles(raw_profiles: List[Dict]) -> List[RadiusProfile]:
        """Convert raw cluster dicts into RadiusProfile objects."""
        profiles = []
        for rp in raw_profiles:
            retail = rp.get('retail', 0)
            civic = rp.get('civic', 0)
            industrial = rp.get('industrial', 0)
            total = retail + civic + industrial
            profiles.append(RadiusProfile(radius_km=rp['radius_km'], retail_entertainment=retail, civic_infrastructure=civic, industrial_infrastructure=industrial, total=total))
        profiles.sort(key=lambda p: p.radius_km)
        return profiles

    def _get_primary_profile(self, profiles: List[RadiusProfile]) -> Optional[RadiusProfile]:
        """Get the profile closest to the primary analysis radius."""
        if not profiles:
            return None
        closest = min(profiles, key=lambda p: abs(p.radius_km - self.primary_radius_km))
        return closest

    def _classify_saturation(self, profiles: List[RadiusProfile]) -> Tuple[SaturationLevel, SaturationLevel, SaturationLevel]:
        """
        Classify saturation for each category based on primary radius counts.
        Returns (retail, civic, industrial) saturation levels.
        """
        primary = self._get_primary_profile(profiles)
        if primary is None:
            return (SaturationLevel.LOW, SaturationLevel.LOW, SaturationLevel.LOW)
        retail_sat = self._classify_single(primary.retail_entertainment, _SATURATION_THRESHOLDS['retail'])
        civic_sat = self._classify_single(primary.civic_infrastructure, _SATURATION_THRESHOLDS['civic'])
        industrial_sat = self._classify_single(primary.industrial_infrastructure, _SATURATION_THRESHOLDS['industrial'])
        return (retail_sat, civic_sat, industrial_sat)

    @staticmethod
    def _classify_single(count: int, thresholds: Tuple[int, int, int]) -> SaturationLevel:
        """Classify a single count into a saturation level."""
        low_max, mod_max, high_max = thresholds
        if count >= high_max:
            return SaturationLevel.CRITICAL
        elif count >= mod_max:
            return SaturationLevel.HIGH
        elif count >= low_max:
            return SaturationLevel.MODERATE
        return SaturationLevel.LOW

    def _compute_overall_score(self, profiles: List[RadiusProfile]) -> float:
        """
        Compute a composite density score (0-100) based on the primary radius.
        Weights: Retail 35%, Civic 30%, Industrial 35%.
        Normalized against max expected density per category.
        """
        primary = self._get_primary_profile(profiles)
        if primary is None:
            return 0.0
        max_density = {'retail': 15.0, 'civic': 10.0, 'industrial': 20.0}
        retail_norm = min(primary.retail_entertainment / max_density['retail'], 1.0)
        civic_norm = min(primary.civic_infrastructure / max_density['civic'], 1.0)
        industrial_norm = min(primary.industrial_infrastructure / max_density['industrial'], 1.0)
        raw_score = retail_norm * 35.0 + civic_norm * 30.0 + industrial_norm * 35.0
        return round(raw_score, 1)

    def _identify_gaps(self, retail_sat: SaturationLevel, civic_sat: SaturationLevel, industrial_sat: SaturationLevel, land: Dict) -> List[Dict]:
        """
        Identify market gaps based on saturation levels.
        Returns ordered list of {category, recommended_usage, rationale, current_usage_viable}.
        """
        gaps = []
        usage = land.get('Allowed_Usage', '')
        saturation_map = {'Retail & Entertainment': retail_sat, 'Civic Infrastructure': civic_sat, 'Industrial Infrastructure': industrial_sat}
        for category, sat_level in saturation_map.items():
            if sat_level in (SaturationLevel.HIGH, SaturationLevel.CRITICAL):
                recommendations = _GAP_RECOMMENDATIONS.get(category, [])
                for rec in recommendations:
                    viable_note = None
                    if self._usage_matches_recommendation(usage, rec['usage']):
                        viable_note = f'Your planned {usage} usage aligns with this gap — competitive positioning is favorable.'
                    elif self._usage_matches_saturated_category(usage, category):
                        viable_note = f"WARNING: Your planned {usage} usage falls in the '{category}' category which is at {sat_level.value} saturation. Strongly consider pivoting to one of the recommended alternatives."
                    gaps.append({'saturated_category': category, 'saturation_level': sat_level.value, 'recommended_usage': rec['usage'], 'rationale': rec['rationale'], 'current_usage_viable': viable_note})
        gaps.sort(key=lambda g: 0 if g.get('current_usage_viable') and 'WARNING' in str(g.get('current_usage_viable', '')) else 1)
        return gaps

    @staticmethod
    def _usage_matches_recommendation(usage: str, recommendation: str) -> bool:
        """Check if the land's usage aligns with a gap recommendation."""
        usage_lower = usage.lower()
        rec_lower = recommendation.lower()
        keyword_map = {'industrial': ['industrial', 'factory', 'manufacturing', 'plant'], 'residential': ['residential', 'housing', 'compound', 'apartment'], 'logistics': ['logistics', 'warehouse', 'distribution', 'hub'], 'agricultural': ['agricultural', 'farming', 'agriculture', 'crop']}
        for _, keywords in keyword_map.items():
            usage_match = any((kw in usage_lower for kw in keywords))
            rec_match = any((kw in rec_lower for kw in keywords))
            if usage_match and rec_match:
                return True
        return False

    @staticmethod
    def _usage_matches_saturated_category(usage: str, category: str) -> bool:
        """Check if the land's usage falls within a saturated category."""
        usage_lower = usage.lower()
        if 'retail' in category.lower() or 'entertainment' in category.lower():
            return False
        if 'civic' in category.lower():
            civic_kw = ['residential']
            return False
        if 'industrial' in category.lower():
            return usage_lower in ('industrial', 'logistics')
        return False

    def _generate_verdict(self, overall_score: float, retail_sat: SaturationLevel, civic_sat: SaturationLevel, industrial_sat: SaturationLevel, land: Dict) -> str:
        """Generate a one-line clustering verdict for the land."""
        sats = [retail_sat, civic_sat, industrial_sat]
        usage = land.get('Allowed_Usage', '')
        if overall_score >= 75:
            verdict = 'Highly clustered zone. Established commercial ecosystem with intense competition. Due diligence on market positioning required.'
        elif overall_score >= 50:
            verdict = 'Moderately developed cluster. Existing service base present with selective opportunities for differentiated development.'
        elif overall_score >= 25:
            verdict = 'Lightly clustered area. Emerging service landscape with first-mover advantages in several categories.'
        else:
            verdict = 'Undeveloped zone with minimal existing services. Greenfield opportunity but requires significant infrastructure investment to attract demand.'
        if usage == 'Industrial' and industrial_sat in (SaturationLevel.HIGH, SaturationLevel.CRITICAL):
            verdict += ' Industrial saturation is elevated — consider specialized manufacturing niches.'
        elif usage == 'Residential' and retail_sat in (SaturationLevel.LOW, SaturationLevel.MODERATE) and (civic_sat in (SaturationLevel.LOW, SaturationLevel.MODERATE)):
            verdict += ' Favorable for residential: low civic/retail saturation indicates unmet demand.'
        return verdict