"""
Smart Land Management Copilot — Advertising Service
====================================================
AI-Driven Cross-Channel Advertising Engine.

Option A: AI Copilot Ad Generation (Free/Self-Service)
  Analyzes land metadata and generates copywriter-grade marketing
  copy for Social Media (Facebook, LinkedIn, X) and SEO metatags.

Option B: Platform-Managed Funded Campaigns (Paid Promotion)
  Deploys targeted ads across search engines and social networks.
  Seller can delegate budget allocation to assigned verified broker(s).
"""
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional
from models.models.auction import AdvertisingCampaign, AdChannel, CampaignStatus
logger = logging.getLogger(__name__)

class AdvertisingService:
    """
    Autonomous marketing module offering two programmatic
    listing promotion paths for sellers/owners.
    """

    def __init__(self):
        self._campaigns: Dict[str, AdvertisingCampaign] = {}

    def create_campaign(self, land_id: str, seller_id: str, campaign_type: str, target_channels: Optional[List[AdChannel]]=None, target_audience: str='', total_budget_egp: float=0.0, delegated_to_broker_id: Optional[str]=None) -> AdvertisingCampaign:
        """
        Create a new advertising campaign.

        Parameters
        ----------
        campaign_type : 'ai_copilot' for free self-service ad generation,
                        'platform_managed' for paid promotion.
        """
        campaign_id = f'CAM-{uuid.uuid4().hex[:8].upper()}'
        channels = target_channels or []
        if campaign_type == 'ai_copilot' and (not channels):
            channels = [AdChannel.FACEBOOK, AdChannel.LINKEDIN, AdChannel.X_TWITTER, AdChannel.SEO_META]
        campaign = AdvertisingCampaign(campaign_id=campaign_id, land_id=land_id, seller_id=seller_id, campaign_type=campaign_type, target_channels=channels, target_audience=target_audience, total_budget_egp=total_budget_egp, delegated_to_broker_id=delegated_to_broker_id, status=CampaignStatus.DRAFT)
        self._campaigns[campaign_id] = campaign
        logger.info(f'Campaign {campaign_id} created: {campaign_type} for land {land_id}')
        return campaign

    def activate_campaign(self, campaign_id: str) -> Optional[AdvertisingCampaign]:
        """Activate a campaign (move from DRAFT to ACTIVE)."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None
        campaign.status = CampaignStatus.ACTIVE
        campaign.last_updated = datetime.now().isoformat()
        logger.info(f'Campaign {campaign_id} activated')
        return campaign

    def pause_campaign(self, campaign_id: str) -> Optional[AdvertisingCampaign]:
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None
        campaign.status = CampaignStatus.PAUSED
        campaign.last_updated = datetime.now().isoformat()
        return campaign

    def complete_campaign(self, campaign_id: str) -> Optional[AdvertisingCampaign]:
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None
        campaign.status = CampaignStatus.COMPLETED
        campaign.last_updated = datetime.now().isoformat()
        return campaign

    def cancel_campaign(self, campaign_id: str) -> Optional[AdvertisingCampaign]:
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None
        campaign.status = CampaignStatus.CANCELLED
        campaign.last_updated = datetime.now().isoformat()
        return campaign

    def get_campaign(self, campaign_id: str) -> Optional[AdvertisingCampaign]:
        return self._campaigns.get(campaign_id)

    def list_campaigns(self, land_id: Optional[str]=None, seller_id: Optional[str]=None, status: Optional[CampaignStatus]=None, campaign_type: Optional[str]=None) -> List[AdvertisingCampaign]:
        results = list(self._campaigns.values())
        if land_id:
            results = [c for c in results if c.land_id == land_id]
        if seller_id:
            results = [c for c in results if c.seller_id == seller_id]
        if status:
            results = [c for c in results if c.status == status]
        if campaign_type:
            results = [c for c in results if c.campaign_type == campaign_type]
        return results

    def get_campaign_stats(self) -> Dict:
        """Return aggregate campaign statistics."""
        campaigns = list(self._campaigns.values())
        return {'total_campaigns': len(campaigns), 'active': sum((1 for c in campaigns if c.status == CampaignStatus.ACTIVE)), 'draft': sum((1 for c in campaigns if c.status == CampaignStatus.DRAFT)), 'completed': sum((1 for c in campaigns if c.status == CampaignStatus.COMPLETED)), 'total_budget_egp': sum((c.total_budget_egp for c in campaigns)), 'total_spent_egp': sum((c.spent_egp for c in campaigns)), 'total_impressions': sum((c.impressions for c in campaigns)), 'total_clicks': sum((c.clicks for c in campaigns)), 'total_leads': sum((c.leads_generated for c in campaigns))}

    def generate_ai_copilot_ads(self, campaign_id: str, land_metadata: Dict) -> Optional[AdvertisingCampaign]:
        """
        Generate optimized marketing copy for social media channels
        and SEO metatags by analyzing the land's metadata.

        This implements Option A (Free/Self-Service). The generated
        copy is tailored based on location, utility status, zoning,
        pricing, and infrastructure availability.
        """
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None
        land_id = land_metadata.get('Land_ID', '')
        governorate = land_metadata.get('Governorate', '')
        region = land_metadata.get('Region_City', '')
        area = land_metadata.get('Total_Area_Sqm', 0)
        price_sqm = land_metadata.get('Price_Per_Sqm_EGP', 0)
        usage = land_metadata.get('Allowed_Usage', '')
        highways = land_metadata.get('Nearest_Highways', '')
        utilities = land_metadata.get('Utilities_Availability', '')
        notes = land_metadata.get('Gov_Feasibility_Notes', '')
        total_price = area * price_sqm
        social_copy = {}
        for channel in campaign.target_channels:
            if channel == AdChannel.SEO_META:
                continue
            social_copy[channel.value] = self._generate_channel_copy(channel=channel.value, land_id=land_id, governorate=governorate, region=region, area=area, price_sqm=price_sqm, total_price=total_price, usage=usage, highways=highways, utilities=utilities, notes=notes)
        campaign.generated_social_copy = social_copy
        seo_meta = self._generate_seo_meta(land_id=land_id, governorate=governorate, region=region, area=area, price_sqm=price_sqm, usage=usage, utilities=utilities, highways=highways)
        campaign.generated_seo_meta = seo_meta
        campaign.last_updated = datetime.now().isoformat()
        logger.info(f'AI Copilot ads generated for campaign {campaign_id}')
        return campaign

    def _generate_channel_copy(self, channel: str, land_id: str, governorate: str, region: str, area: int, price_sqm: float, total_price: float, usage: str, highways: str, utilities: str, notes: str) -> str:
        """Generate channel-specific marketing copy based on land metadata."""
        area_feddan = round(area / 4200, 1)
        location_str = f'{region}, {governorate}'
        if channel == AdChannel.FACEBOOK.value:
            return f"Investment Opportunity: {area:,} sqm ({area_feddan} feddan) {usage} Land — {location_str}\n\nPrice: {price_sqm:,} EGP/sqm | Total: {total_price:,.0f} EGP\n\nInfrastructure: {utilities}\nHighway Access: {highways}\n\n{(notes[:200] if notes else 'Prime location with strong growth potential in the Egyptian real estate market.')}\n\nContact us for due diligence reports and site visits. Verified title deeds. Shahr Eqary registered.\n\n#EgyptRealEstate #{usage}Land #{governorate.replace(' ', '')}Investment #LandForSale #SmartLandCopilot"
        elif channel == AdChannel.LINKEDIN.value:
            return f"Strategic Land Acquisition Opportunity — {location_str}\n\nWe are pleased to present a {area:,} sqm ({area_feddan} feddan) {usage}-zoned parcel positioned for {usage.lower()} development.\n\nKey Metrics:\n  - Price per sqm: {price_sqm:,} EGP\n  - Total asking price: {total_price:,.0f} EGP\n  - Zoning: {usage}\n  - Utilities: {utilities}\n  - Highway access: {highways}\n\n{(notes[:250] if notes else 'This parcel offers compelling ROI potential backed by Egyptian government development incentives and growing infrastructure.')}\n\nRef: {land_id} | Due diligence available upon request.\n\n#PropTech #EgyptInvestment #{usage} #LandAcquisition #RealEgypt"
        elif channel == AdChannel.X_TWITTER.value:
            return f'{area:,} sqm {usage} land in {region}, {governorate} — {price_sqm:,} EGP/sqm ({total_price:,.0f} EGP total). Utilities: {utilities}. {highways}. Verified title. DM for details. #EgyptRealEstate #Land'
        elif channel == AdChannel.INSTAGRAM.value:
            return f"Premium {usage} Land — {location_str}\n\n{area:,} sqm | {price_sqm:,} EGP/sqm\n{total_price:,.0f} EGP total\n\nInfrastructure: {utilities}\nAccess: {highways}\n\nDM for investment brief & site visit scheduling.\n\n#EgyptRealEstate #LandInvestment #{usage} #{governorate.replace(' ', '')}Land"
        elif channel == AdChannel.GOOGLE_SEARCH.value:
            return f'Buy {usage} Land in {region}, {governorate} — {area:,} sqm at {price_sqm:,} EGP/sqm. Total: {total_price:,.0f} EGP. {utilities}. {highways}. Verified title deeds. View details and schedule a site visit today.'
        return f'{usage} Land for Sale — {location_str}, {area:,} sqm, {price_sqm:,} EGP/sqm'

    def _generate_seo_meta(self, land_id: str, governorate: str, region: str, area: int, price_sqm: float, usage: str, utilities: str, highways: str) -> Dict[str, str]:
        """Generate SEO metatags for the land listing."""
        location_str = f'{region}, {governorate}'
        title = f'{usage} Land for Sale in {location_str} — {area:,} sqm at {price_sqm:,} EGP/sqm | Smart Land Copilot'
        description = f'Explore this {area:,} sqm {usage.lower()}-zoned land in {location_str}, Egypt. Priced at {price_sqm:,} EGP per square meter with {utilities} infrastructure. Access via {highways}. Verified title deeds. View investment analysis, feasibility reports, and schedule site visits.'
        keywords = f'{usage.lower()} land for sale, {governorate.lower()} real estate, {region.lower()} land investment, Egypt {usage.lower()} property, {price_sqm:,} EGP per sqm, {area:,} sqm land, Egyptian real estate market, Smart Land Copilot'
        og_title = f'{usage} Land — {location_str} | {area:,} sqm'
        og_description = f"{area:,} sqm {usage} parcel in {location_str} at {price_sqm:,} EGP/sqm. Full infrastructure: {utilities}. Invest in Egypt's growing real estate market."
        return {'title': title, 'description': description, 'keywords': keywords, 'og_title': og_title, 'og_description': og_description}

    def deploy_paid_campaign(self, campaign_id: str, impressions: int=0, clicks: int=0, leads: int=0, spent: float=0.0) -> Optional[AdvertisingCampaign]:
        """
        Simulate campaign deployment and update performance metrics.
        In production, this would integrate with ad platform APIs.
        """
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None
        if campaign.campaign_type != 'platform_managed':
            return None
        campaign.status = CampaignStatus.ACTIVE
        campaign.impressions += impressions
        campaign.clicks += clicks
        campaign.leads_generated += leads
        campaign.spent_egp = round(campaign.spent_egp + spent, 2)
        campaign.last_updated = datetime.now().isoformat()
        return campaign
_advertising_service: Optional[AdvertisingService] = None

def get_advertising_service() -> AdvertisingService:
    global _advertising_service
    if _advertising_service is None:
        _advertising_service = AdvertisingService()
        _seed_sample_campaigns(_advertising_service)
    return _advertising_service

def _seed_sample_campaigns(svc: AdvertisingService) -> None:
    """Seed with sample advertising campaigns."""
    from data.land_database import get_all_lands
    lands = get_all_lands()
    for land in lands[:3]:
        camp = svc.create_campaign(land_id=land['Land_ID'], seller_id='USR-00000002', campaign_type='ai_copilot', target_audience='Investors and developers looking for premium Egyptian land')
        svc.generate_ai_copilot_ads(camp.campaign_id, land)
        svc.activate_campaign(camp.campaign_id)
        svc.deploy_paid_campaign(camp.campaign_id, impressions=4500 + hash(land['Land_ID']) % 5000, clicks=120 + hash(land['Land_ID']) % 200, leads=8 + hash(land['Land_ID']) % 15, spent=3500.0 + hash(land['Land_ID']) % 5000)