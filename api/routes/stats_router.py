"""
مسار الإحصائيات والصحة — StatsRouter
=======================================
GET /accounts/health  → فحص الصحة
GET /accounts/stats    → إحصائيات عامة
"""
import time
import logging

from fastapi import APIRouter

from core.domain.entities import HealthResponse, APIResponse
from api.routes._deps import get_investor_store, get_landowner_store, lands_catalog_global

logger = logging.getLogger(__name__)

SERVICE_START = time.time()
SERVICE_VERSION = "1.0.0"

router = APIRouter(prefix="/api/v1", tags=["stats"])


@router.get("/accounts/health", response_model=HealthResponse)
async def health():
    """فحص صحة خدمة الحسابات"""
    inv_store = get_investor_store()
    lo_store = get_landowner_store()
    return HealthResponse(
        service="account-service",
        status="healthy",
        version=SERVICE_VERSION,
        uptime_seconds=round(time.time() - SERVICE_START, 1),
        dependencies={
            "investor_store": f"{inv_store.count()} مستثمر",
            "landowner_store": f"{lo_store.count()} مالك أرض",
            "lands_catalog": f"{len(lands_catalog_global)} أرض",
        },
    )


@router.get("/accounts/stats", response_model=APIResponse)
async def account_stats():
    """إحصائيات عامة لخدمة الحسابات."""
    inv_store = get_investor_store()
    lo_store = get_landowner_store()

    investors = inv_store.get_all()
    total_wallet = sum(inv["wallet_balance_egp"] for inv in investors)
    total_frozen = sum(inv["frozen_balance_egp"] for inv in investors)
    total_loyalty = sum(inv["loyalty_points"] for inv in investors)
    total_purchased = sum(inv["total_lands_purchased"] for inv in investors)
    total_spent = sum(inv["total_spent_egp"] for inv in investors)

    landowners = lo_store.get_all()
    total_sales = sum(lo["total_sales_egp"] for lo in landowners)
    total_lands_listed = sum(lo["total_lands_listed"] for lo in landowners)
    total_active_lands = sum(lo["active_lands_count"] for lo in landowners)
    total_commission = sum(lo["total_commission_earned_egp"] for lo in landowners)

    return APIResponse(
        data={
            "investors": {
                "count": len(investors),
                "total_wallet_egp": round(total_wallet, 2),
                "total_frozen_egp": round(total_frozen, 2),
                "total_available_egp": round(total_wallet - total_frozen, 2),
                "total_loyalty_points": total_loyalty,
                "total_lands_purchased": total_purchased,
                "total_spent_egp": round(total_spent, 2),
            },
            "landowners": {
                "count": len(landowners),
                "total_sales_egp": round(total_sales, 2),
                "total_lands_listed": total_lands_listed,
                "active_lands_count": total_active_lands,
                "total_commission_earned_egp": round(total_commission, 2),
            },
            "platform": {
                "lands_in_catalog": len(lands_catalog_global),
                "available_lands": sum(
                    1 for l in lands_catalog_global.values()
                    if l.get("investment_status") == "متاح"
                ),
                "sold_lands": sum(
                    1 for l in lands_catalog_global.values()
                    if l.get("investment_status") == "مباع"
                ),
            },
        },
        message="إحصائيات خدمة الحسابات",
    )
