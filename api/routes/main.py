"""
Smart Land Management Copilot — Purchase Module
FastAPI application entry point.

Run:
    uvicorn purchase_module.main:app --reload --port 8000

Test:
    pytest purchase_module/tests/ -v
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from purchase_module.database import init_db
from purchase_module.routers import investors_router, landowners_router, payments_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Startup: create DB tables. Shutdown: cleanup."""
    logger.info("Starting Smart Land Purchase Module...")
    await init_db()
    logger.info("Database tables initialized.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Smart Land — Purchase Module",
    description=(
        "Complete land purchase system with payment gateway integration "
        "(Fawry / Stripe), investor & landowner accounts, loyalty points, "
        "and purchase incentive engine."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(payments_router)
app.include_router(investors_router)
app.include_router(landowners_router)


# ──────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "smart-land-purchase"}


@app.get("/", tags=["System"])
async def root():
    return {
        "service": "Smart Land Purchase Module",
        "docs": "/docs",
        "version": "1.0.0",
    }