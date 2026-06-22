"""
Account Service — خدمة الحسابات (تكوين المسارات)
==================================================
يُجمّع كل المسارات الفرعية في تطبيق FastAPI واحد.

نقاط النهاية:
    ── المستثمرون ──
    POST   /api/v1/investors                    → إنشاء حساب مستثمر
    GET    /api/v1/investors/{id}               → بيانات المستثمر
    GET    /api/v1/investors/{id}/wallet        → بيانات المحفظة
    GET    /api/v1/investors/{id}/transactions  → سجل معاملات المحفظة
    POST   /api/v1/investors/{id}/deposit       → إيداع في المحفظة
    POST   /api/v1/investors/{id}/withdraw      → سحب من المحفظة
    POST   /api/v1/investors/{id}/redeem-loyalty → استبدال نقاط الولاء
    GET    /api/v1/investors                     → قائمة المستثمرين

    ── ملاك الأراضي ──
    POST   /api/v1/landowners                   → إنشاء حساب مالك
    GET    /api/v1/landowners/{id}              → بيانات المالك
    GET    /api/v1/landowners/{id}/lands        → أراضي المالك
    PUT    /api/v1/landowners/{id}/commission   → تحديث نسبة العمولة
    POST   /api/v1/landowners/{id}/list-land    → إعلان أرض جديدة
    GET    /api/v1/landowners                    → قائمة الملاك

    ── نقل الملكية ──
    POST   /api/v1/transfer-ownership           → نقل ملكية أرض

    ── الصحة والإحصائيات ──
    GET    /api/v1/accounts/health              → فحص صحة الخدمة
    GET    /api/v1/accounts/stats               → إحصائيات عامة
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.broker import router as broker_router
from api.routes.investor_router import router as investor_router
from api.routes.land import router as land_verification_router
from api.routes.landowner_router import router as landowner_router
from api.routes.stats_router import router as stats_router
from api.routes.transfer_router import router as transfer_router

SERVICE_VERSION = "1.0.0"
SERVICE_PORT = int(os.getenv("ACCOUNT_SERVICE_PORT", "8004"))

app = FastAPI(
    title="Smart Land — Account Service",
    description="خدمة الحسابات متعددة الأدوار (المستثمرون + ملاك الأراضي)",
    version=SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(investor_router)
app.include_router(landowner_router)
app.include_router(transfer_router)
app.include_router(stats_router)
app.include_router(broker_router)
app.include_router(land_verification_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.routes.account:app", host="0.0.0.0", port=SERVICE_PORT, reload=True)
