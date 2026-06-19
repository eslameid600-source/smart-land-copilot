"""
Core Business Logic Services
=============================
This file was auto-merged on import-migration to preserve all package-level
exports and imports discovered in the project root. It intentionally wraps
submodule imports in try/except blocks to avoid import-time crashes during
reorg. If you need a specific symbol exported at package level, adjust this
file accordingly.
"""
try:
    from purchase_module.services.payment_service import PaymentService
    from purchase_module.services.investor_service import InvestorService
    from purchase_module.services.landowner_service import LandownerService
    from purchase_module.routers.payments import router as payments_router
except Exception:
    pass
try:
    from core.customer_service.hub import CustomerServiceHub
    from core.customer_service.rag_chatbot import RAGChatbot
    from core.customer_service.survey_service import SurveyService
except Exception:
    pass
try:
    from core.geological.service import GeologicalService
    from core.geological.soil_service import SoilService
    from core.geological.groundwater_service import GroundwaterService
except Exception:
    pass
try:
    from infrastructure.monitoring.metrics_middleware import MetricsMiddleware
    from infrastructure.monitoring.sentry_init import init_sentry
except Exception:
    pass
try:
    from core.financial.service import FinancialService
except Exception:
    pass
try:
    from core.matchmaking.service import MatchmakingService
    from core.auction.engine import AuctionEngine
except Exception:
    pass
try:
    from core.account.models import Investor, Landowner, WalletTransaction, OwnedLand
    from core.account.store import InvestorStore, LandownerStore, transfer_ownership
except Exception:
    pass
try:
    from core.notification.models import Notification, UserNotificationPreference
except Exception:
    pass
try:
    from data.land_database import LANDS_RAW, USAGE_COLORS, ALL_UTILITIES, get_all_lands, get_land_dataframe, get_land_by_id, get_usage_categories, get_governorates, get_auction_lands, summary_stats
except Exception:
    pass
try:
    from services.financial_service import FinancialService as _FinancialService
    from services.prediction_service import PredictionService
    from services.recommendation_service import RecommendationEngine
    from services.customer_service import CustomerServiceSystem
    from services.feasibility_service import FeasibilityReportService
    from services.etl_service import ETLService
    from services.metrics_service import ProjectMetricsService, get_metrics_service
    from services.auction_service import AuctionEngine as _AuctionEngine2, CommissionCalculator, LandSourcingService, get_auction_engine, get_sourcing_service
except Exception:
    pass
try:
    from models.models.land import LandRecord, GeologicalData, InfrastructureData, LogisticsMeta, FleetMaintenanceImpact, FuelTripEstimate, AirFreightConnectivity, RailFreightIntegration, RoadQuality, FuelType, CargoAirportTier, RailNetworkType, UsageType, InvestmentStatus, ListingStatus, ListingIntent, GreeneryDensityData, CreatorStudioSuitability, EnvironmentalData, BrokerAllocation, LandListingMeta
    from models.models.investor import InvestorCriteria
    from models.models.financial import FinancialAnalysis, CashFlowEntry, TaxBreakdown
    from models.models.matchmaking import MatchResult
    from models.models.prediction import PricePrediction
    from models.models.ticket import SupportTicket, TicketStatus
    from models.models.auction import AuctionRecord, AuctionStatus, Bid, BidStatus, TransactionFeeBreakdown, LandLead, LeadStatus, ListingSource, BrokerCommissionRecord, AdChannel, CampaignStatus, AdvertisingCampaign
    from models.models.user import UserAccount, UserRole, BrokerVerificationStatus, ListingIntent as UserListingIntent, DocumentType, BrokerDocument
except Exception:
    pass
try:
    __all__ += ['PaymentService', 'GeologicalService', 'CustomerServiceHub', 'RAGChatbot', 'MatchmakingService', 'AuctionEngine', 'InvestorStore', 'LandownerStore', 'MetricsMiddleware']
except NameError:
    __all__ = ['PaymentService', 'GeologicalService', 'CustomerServiceHub', 'RAGChatbot', 'MatchmakingService', 'AuctionEngine', 'InvestorStore', 'LandownerStore', 'MetricsMiddleware']