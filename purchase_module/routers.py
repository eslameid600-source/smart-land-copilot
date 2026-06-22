"""purchase_module.routers — facade aggregating the project routers.

Exports both singular and plural aliases so legacy imports keep working:
    from purchase_module.routers import investors_router, landowners_router, payments_router  # legacy
    from purchase_module.routers import investor_router, landowner_router, transfer_router    # new
"""


from api.routes.investor_router import router as investor_router  # noqa: F401
from api.routes.landowner_router import router as landowner_router  # noqa: F401
from api.routes.transfer_router import router as transfer_router  # noqa: F401

# Legacy plural aliases (used by api/routes/main.py)
investors_router = investor_router
landowners_router = landowner_router
payments_router = transfer_router

__all__ = [
    "investor_router",
    "landowner_router",
    "transfer_router",
    "investors_router",
    "landowners_router",
    "payments_router",
]
