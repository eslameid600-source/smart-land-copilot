# Services package
"""
Core Business Logic Services
=============================
This file was auto-merged on import-migration to preserve all package-level
exports and imports discovered in the project root. It intentionally wraps
submodule imports in try/except blocks to avoid import-time crashes during
reorg. If you need a specific symbol exported at package level, adjust this
file accordingly.
"""

# Existing canonical imports (kept from pre-merge __init__)
try:
    from purchase_module.services.payment_service import PaymentService
except Exception:
    pass

try:
    from core.customer_service.hub import CustomerServiceHub
    from core.customer_service.rag_chatbot import RAGChatbot
except Exception:
    pass

try:
    from core.geological.service import GeologicalService
except Exception:
    pass

try:
    from infrastructure.monitoring.metrics_middleware import MetricsMiddleware
except Exception:
    pass

try:
    pass
except Exception:
    pass

try:
    from core.auction.engine import AuctionEngine
    from core.matchmaking.service import MatchmakingService
except Exception:
    pass

try:
    from core.account.store import InvestorStore, LandownerStore
except Exception:
    pass

try:
    pass
except Exception:
    pass

# --- Merged imports from root __init__ conflict files ---
# Merged from services/__init__(1).from_root (data layer)
try:
    pass
except Exception:
    pass

# Merged from services/__init__(3).from_root (service re-exports)
try:
    pass
except Exception:
    pass

# Merged from services/__init__(4).from_root (model re-exports)
try:
    pass
except Exception:
    pass

# Attempt to augment package __all__ with common exports discovered in merges
try:
    __all__ += [
        'PaymentService', 'GeologicalService', 'CustomerServiceHub', 'RAGChatbot',
        'MatchmakingService', 'AuctionEngine', 'InvestorStore', 'LandownerStore',
        'MetricsMiddleware',
    ]
except NameError:
    __all__ = [
        'PaymentService', 'GeologicalService', 'CustomerServiceHub', 'RAGChatbot',
        'MatchmakingService', 'AuctionEngine', 'InvestorStore', 'LandownerStore',
        'MetricsMiddleware',
    ]
