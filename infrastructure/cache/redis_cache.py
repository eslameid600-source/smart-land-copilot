"""
Smart Land Copilot — Redis Cache Layer
========================================
Fast caching for slow API endpoints, Streamlit data, and predictions.

Features:
    - `cached()` decorator for async functions
    - `st_cache_data()` for Streamlit @st.cache_data replacement
    - `invalidate_cache()` to clear stale entries
    - Separate TTL for different endpoint types
"""

import hashlib
import json
import logging
import os
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Redis Connection
# ──────────────────────────────────────────────

_redis_client = None


def get_redis() -> Optional[any]:
    """Get or create Redis client (lazy init). Returns None if unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD", None),
            db=int(os.getenv("REDIS_CACHE_DB", "1")),
            socket_timeout=2,
            socket_connect_timeout=2,
            retry_on_timeout=True,
            decode_responses=True,
        )
        logger.info("Redis cache client initialized")
        return _redis_client
    except ImportError:
        logger.warning("redis.asyncio not installed — cache disabled")
        return None
    except Exception as e:
        logger.warning(f"Redis connection failed — cache disabled: {e}")
        return None


async def close_redis():
    """Close Redis connection gracefully."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# ──────────────────────────────────────────────
# TTL Configuration (in seconds)
# ──────────────────────────────────────────────

CACHE_TTL = {
    # Predictions — slow ML inference
    "predictions:market-overview": timedelta(hours=6).total_seconds(),
    "predictions:price-trend": timedelta(hours=24).total_seconds(),
    # Maps — large GeoJSON data
    "maps:tiles": timedelta(hours=12).total_seconds(),
    "maps:pois": timedelta(hours=1).total_seconds(),
    # Dashboard — materialized views (already fast, but cache for burst)
    "dashboard:bi": timedelta(minutes=15).total_seconds(),
    "dashboard:kpis": timedelta(minutes=5).total_seconds(),
    # Lands catalog — changes infrequently
    "lands:catalog": timedelta(minutes=30).total_seconds(),
    "lands:search": timedelta(minutes=5).total_seconds(),
    # Default
    "default": timedelta(minutes=10).total_seconds(),
}


def _get_ttl(key: str) -> int:
    """Get TTL for a specific cache key pattern."""
    for pattern, ttl in CACHE_TTL.items():
        if pattern in key:
            return int(ttl)
    return int(CACHE_TTL["default"])


def _make_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate deterministic cache key from function name + arguments."""
    key_parts = [prefix]
    if args:
        key_parts.append(str(args))
    if kwargs:
        key_parts.append(str(sorted(kwargs.items())))
    key_str = ":".join(key_parts)
    key_hash = hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"smartland:{prefix}:{key_hash}"


# ──────────────────────────────────────────────
# Async Caching Decorator
# ──────────────────────────────────────────────

def cached(ttl_override: Optional[int] = None):
    """
    Async decorator that caches function results in Redis.

    Usage:
        @cached(ttl_override=300)
        async def get_market_overview():
            ...

    The cache key is auto-derived from function name + arguments.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            redis = get_redis()
            if redis is None:
                # Redis unavailable — fall through to real function
                return await func(*args, **kwargs)

            cache_key = _make_cache_key(func.__name__, *args, **kwargs)
            ttl = ttl_override if ttl_override else _get_ttl(cache_key)

            try:
                # Try cache first
                cached_data = await redis.get(cache_key)
                if cached_data is not None:
                    logger.debug(f"Cache HIT: {cache_key}")
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")

            # Cache miss — execute real function
            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)

            # Store in cache (only if not None)
            if result is not None:
                try:
                    serialized = json.dumps(result, default=str)
                    await redis.setex(cache_key, int(ttl), serialized)
                except Exception as e:
                    logger.warning(f"Cache write error: {e}")

            return result

        return wrapper
    return decorator


# ──────────────────────────────────────────────
# Cache Invalidation
# ──────────────────────────────────────────────

async def invalidate_cache(pattern: str) -> int:
    """
    Invalidate all cache entries matching a pattern.

    Usage:
        await invalidate_cache("predictions:*")  # Clear all predictions
        await invalidate_cache("maps:*")          # Clear all map tiles
    """
    redis = get_redis()
    if redis is None:
        return 0

    try:
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await redis.scan(
                cursor=cursor, match=f"smartland:{pattern}", count=100
            )
            if keys:
                deleted += await redis.delete(*keys)
            if cursor == 0:
                break
        logger.info(f"Cache invalidated: {pattern} → {deleted} keys deleted")
        return deleted
    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")
        return 0


async def invalidate_all() -> int:
    """Clear entire cache (use with caution)."""
    return await invalidate_cache("*")


# ──────────────────────────────────────────────
# Cache Status / Health
# ──────────────────────────────────────────────

async def cache_health() -> Dict[str, any]:
    """Check Redis cache health and stats."""
    redis = get_redis()
    if redis is None:
        return {"status": "unavailable", "reason": "Redis not connected"}

    try:
        info = await redis.info()
        db_size = await redis.dbsize()
        return {
            "status": "healthy",
            "redis_version": info.get("redis_version", "unknown"),
            "total_keys": db_size,
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "uptime_days": info.get("uptime_in_days", 0),
            "connected_clients": info.get("connected_clients", 0),
        }
    except Exception as e:
        return {"status": "error", "reason": str(e)}


# ──────────────────────────────────────────────
# Direct Cache Operations
# ──────────────────────────────────────────────

async def get_cache(key: str) -> Optional[Any]:
    """Get a value from cache by exact key."""
    redis = get_redis()
    if redis is None:
        return None
    try:
        data = await redis.get(f"smartland:{key}")
        return json.loads(data) if data else None
    except Exception:
        return None


async def set_cache(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Set a value in cache with optional TTL."""
    redis = get_redis()
    if redis is None:
        return False
    try:
        serialized = json.dumps(value, default=str)
        ttl = ttl or _get_ttl(key)
        await redis.setex(f"smartland:{key}", int(ttl), serialized)
        return True
    except Exception as e:
        logger.warning(f"Cache set error: {e}")
        return False