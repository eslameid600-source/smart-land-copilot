# -*- coding: utf-8 -*-
"""
api/routes/main.py
==================

نقطة دخول تطبيق FastAPI الرئيسي مع تضمين Rate Limiting.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from api.middleware.rate_limit import init_rate_limiting, limiter

app = FastAPI(title="Smart Land Copilot API")

init_rate_limiting(app)


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy"}


@app.get("/investors/me")
@limiter.limit("100/minute")
async def investor_me(request: Request) -> dict:
    return {"id": "me"}


@app.post("/lands/purchase")
@limiter.limit("100/minute")
async def purchase_land(request: Request) -> dict:
    return {"status": "purchased"}


@app.post("/auctions/bid")
@limiter.limit("100/minute")
async def place_bid(request: Request) -> dict:
    return {"status": "bid_placed"}


@app.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request) -> dict:
    return {"access_token": "..."}
