"""
Smart Land Management Copilot — Recommendation Engine
=======================================================
Generates dynamic investment recommendations based on
current market data, trends, and urgency signals.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from models.models.models.prediction import PricePrediction
from models.models.models.land import SaturationLevel
from services.prediction_service import PredictionService
from services.density_service import DensityService
from services.logistics_service import LogisticsService

class RecommendationEngine:
    """
    Produces actionable, time-sensitive recommendations for investors.
    Analyzes market signals to generate urgency-driven advice.
    """

    def __init__(self, prediction_service: Optional[PredictionService]=None):
        self.pred_svc = prediction_service or PredictionService()
        self.density_svc = DensityService()
        self.logistics_svc = LogisticsService()

    def generate_recommendations(self, lands: List[Dict], max_recommendations: int=5) -> List[Dict]:
        """
        Analyze all lands and generate prioritized recommendations.

        Each recommendation includes:
        - Land ID and brief description
        - Urgency level (Buy Now / Consider / Watch)
        - Key reasoning
        - Time-sensitive opportunity
        - Expected return timeframe
        """
        predictions = self.pred_svc.predict_all(lands, horizon_months=6)
        today = datetime.now()
        scored: List[Dict] = []
        for land, pred in zip(lands, predictions):
            score = 0.0
            reasons = []
            urgency = 'Watch'
            if pred.predicted_change_pct > 15:
                score += 30
                reasons.append(f'Strong {pred.predicted_change_pct:.0f}% projected growth in 6 months')
                urgency = 'Buy Now'
            elif pred.predicted_change_pct > 8:
                score += 20
                reasons.append(f'Solid {pred.predicted_change_pct:.0f}% growth projected')
                urgency = 'Consider'
            elif pred.predicted_change_pct > 3:
                score += 10
                reasons.append(f'Modest {pred.predicted_change_pct:.0f}% appreciation expected')
                urgency = 'Consider'
            if land['Investment_Status'] == 'Public Auction' and land.get('Auction_Date'):
                auction_date = datetime.strptime(land['Auction_Date'], '%Y-%m-%d')
                days_until = (auction_date - today).days
                if 0 < days_until <= 90:
                    score += 25
                    reasons.append(f'Auction in {days_until} days — time-sensitive opportunity')
                    if urgency != 'Buy Now':
                        urgency = 'Buy Now'
                elif 90 < days_until <= 180:
                    score += 15
                    reasons.append(f"Auction scheduled for {land['Auction_Date']}")
                    if urgency == 'Watch':
                        urgency = 'Consider'
            utilities = land['Utilities_Availability'].split(', ')
            utility_score = len(utilities) / 4.0
            score += utility_score * 20
            if len(utilities) >= 4:
                reasons.append('All 4 utilities available — ready for development')
            trend = land.get('Market_Trend', 'Stable')
            if trend == 'Rising Fast':
                score += 15
                reasons.append('Rapid market appreciation trend')
            elif trend == 'Rising':
                score += 10
                reasons.append('Upward price trajectory')
            elif trend == 'Stable Rising':
                score += 7
            volume = land.get('Avg_Transaction_Volume', 0)
            if volume > 10:
                score += 10
                reasons.append(f'High liquidity: {volume} avg monthly transactions')
            elif volume > 5:
                score += 5
            density_analysis = self.density_svc.analyze(land)
            density_score = 0.0
            if density_analysis.overall_density_score < 15:
                density_score = 15
                reasons.append('Undeveloped zone — first-mover advantage with minimal competition')
            elif density_analysis.overall_density_score < 30:
                density_score = 12
                reasons.append('Lightly clustered — favorable entry with low saturation')
            elif density_analysis.overall_density_score < 50:
                density_score = 8
                reasons.append('Moderate clustering — selective opportunities exist')
            elif density_analysis.overall_density_score < 75:
                density_score = 4
                reasons.append('Developed cluster — some competition expected')
            else:
                density_score = 1
                reasons.append('Dense zone — high competition, differentiation required')
            usage = land['Allowed_Usage']
            if usage in ('Industrial', 'Logistics') and density_analysis.industrial_infrastructure_saturation in (SaturationLevel.HIGH, SaturationLevel.CRITICAL):
                density_score = max(density_score - 5, 0)
                reasons.append(f'Industrial saturation {density_analysis.industrial_infrastructure_saturation.value} — consider niche positioning')
            if density_analysis.market_gap_analysis:
                aligned_gaps = [g for g in density_analysis.market_gap_analysis if g.get('current_usage_viable') and 'WARNING' not in str(g.get('current_usage_viable', ''))]
                if aligned_gaps:
                    density_score = min(density_score + 3, 15)
                    reasons.append(f'Market gap aligned with {usage} usage — competitive advantage')
            score += density_score
            logistics_analysis = self.logistics_svc.analyze(land)
            if usage in ('Logistics', 'Industrial'):
                log_score = logistics_analysis.accessibility_score / 100.0 * 15.0
                if logistics_analysis.accessibility_score >= 70:
                    reasons.append(f'Excellent logistics score {logistics_analysis.accessibility_score:.0f}/100 — multimodal access')
                elif logistics_analysis.accessibility_score >= 50:
                    reasons.append(f'Good logistics infrastructure (score {logistics_analysis.accessibility_score:.0f}/100)')
                elif logistics_analysis.accessibility_score < 30:
                    log_score = max(log_score - 3, 0)
                    reasons.append(f'Low logistics accessibility ({logistics_analysis.accessibility_score:.0f}/100) — may increase operating costs')
                if logistics_analysis.fleet_maintenance:
                    fm = logistics_analysis.fleet_maintenance
                    if fm.maintenance_overhead_pct >= 50:
                        log_score = max(log_score - 2, 0)
                        reasons.append(f'High fleet maintenance overhead (+{fm.maintenance_overhead_pct:.0f}%)')
                    elif fm.maintenance_overhead_pct == 0:
                        log_score = min(log_score + 1, 15)
                        reasons.append('Zero fleet maintenance overhead (Excellent roads)')
                if logistics_analysis.rail_freight and logistics_analysis.rail_freight.heavy_tonnage_viable:
                    rf = logistics_analysis.rail_freight
                    log_score = min(log_score + 1.5, 15)
                    reasons.append(f'Rail heavy-tonnage viable ({rf.network_type.value}, -{rf.estimated_tonnage_cost_saving_pct:.0f}% cost)')
                if logistics_analysis.air_freight and logistics_analysis.air_freight.airport_tier.value == 'Tier-1 Major' and (logistics_analysis.air_freight.trucking_transit_hours <= 1.5):
                    log_score = min(log_score + 1, 15)
                    reasons.append(f'Tier-1 cargo airport within {logistics_analysis.air_freight.trucking_transit_hours:.1f}h')
                score += log_score
            scored.append({'land_id': land['Land_ID'], 'governorate': land['Governorate'], 'region': land['Region_City'], 'usage': land['Allowed_Usage'], 'current_price_sqm': land['Price_Per_Sqm_EGP'], 'predicted_change_pct': pred.predicted_change_pct, 'confidence': pred.confidence_pct, 'urgency': urgency, 'action_score': round(score, 1), 'reasons': reasons, 'prediction': pred, 'is_auction': land['Investment_Status'] == 'Public Auction', 'auction_date': land.get('Auction_Date'), 'density_score': density_analysis.overall_density_score, 'density_verdict': density_analysis.clustering_verdict, 'logistics_score': logistics_analysis.accessibility_score, 'logistics_verdict': logistics_analysis.logistics_verdict})
        scored.sort(key=lambda x: x['action_score'], reverse=True)
        return scored[:max_recommendations]

    def format_recommendation_text(self, rec: Dict) -> str:
        """Format a single recommendation as readable text for LLM context."""
        urgency_emoji = {'Buy Now': '[URGENT]', 'Consider': '[RECOMMENDED]', 'Watch': '[MONITOR]'}
        tag = urgency_emoji.get(rec['urgency'], '')
        lines = [f"{tag} {rec['land_id']} — {rec['governorate']}: {rec['region']}", f"  Usage: {rec['usage']} | Current: {rec['current_price_sqm']:,.0f} EGP/m²", f"  6-Month Forecast: +{rec['predicted_change_pct']:.1f}% (confidence: {rec['confidence']:.0f}%)", f"  Urgency: {rec['urgency']} (Score: {rec['action_score']}/100)"]
        for reason in rec['reasons'][:4]:
            lines.append(f'  - {reason}')
        if rec['is_auction'] and rec['auction_date']:
            lines.append(f"  AUCTION DATE: {rec['auction_date']}")
        if rec.get('density_verdict'):
            lines.append(f"  Clustering: {rec['density_verdict']}")
        return '\n'.join(lines)