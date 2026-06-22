"""
Smart Land Copilot — Database Optimizations
=============================================
Indexes, Materialized Views, and scheduled refresh for BI Dashboard.

This module provides:
    1. `create_indexes()` — Creates performance indexes on key tables
    2. `create_materialized_views()` — Creates MV for BI Dashboard
    3. `refresh_materialized_views()` — Scheduled daily refresh
    4. `get_bi_dashboard_data()` — Fast query via Materialized Views
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Index Creation SQL
# ──────────────────────────────────────────────

INDEXES_SQL = """
-- 1. lands table indexes
CREATE INDEX IF NOT EXISTS ix_lands_price_per_sqm
    ON lands (price_per_sqm_egp);

CREATE INDEX IF NOT EXISTS ix_lands_governorate
    ON lands (governorate);

CREATE INDEX IF NOT EXISTS ix_lands_status
    ON lands (status);

CREATE INDEX IF NOT EXISTS ix_lands_owner_status
    ON lands (owner_id, status);

-- 2. transactions table indexes
CREATE INDEX IF NOT EXISTS ix_transactions_buyer_created
    ON transactions (buyer_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_transactions_seller_created
    ON transactions (seller_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_transactions_land_id
    ON transactions (land_id);

CREATE INDEX IF NOT EXISTS ix_transactions_status_created
    ON transactions (status, created_at DESC);

-- 3. broker_land_assignments indexes
CREATE INDEX IF NOT EXISTS ix_broker_assign_broker_land
    ON broker_land_assignments (broker_id, land_id);

CREATE INDEX IF NOT EXISTS ix_broker_assign_land_broker
    ON broker_land_assignments (land_id, broker_id);

CREATE INDEX IF NOT EXISTS ix_broker_assign_status
    ON broker_land_assignments (assignment_status);

-- 4. notification table indexes (already in notifications.py, ensure they exist)
CREATE INDEX IF NOT EXISTS ix_notif_user_id ON notifications (user_id);
CREATE INDEX IF NOT EXISTS ix_notif_user_unread ON notifications (user_id, is_read);
CREATE INDEX IF NOT EXISTS ix_notif_type ON notifications (type);
CREATE INDEX IF NOT EXISTS ix_notif_created ON notifications (created_at DESC);
"""

# ──────────────────────────────────────────────
# Materialized Views for BI Dashboard
# ──────────────────────────────────────────────

MATERIALIZED_VIEWS_SQL = """
-- MV 1: Daily summary statistics
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bi_daily_summary AS
SELECT
    DATE(created_at) AS date,
    COUNT(*) AS total_transactions,
    COUNT(DISTINCT buyer_id) AS unique_buyers,
    COUNT(DISTINCT seller_id) AS unique_sellers,
    COALESCE(SUM(amount_egp), 0) AS total_sales_volume_egp,
    COALESCE(AVG(amount_egp), 0) AS avg_transaction_value_egp,
    COALESCE(SUM(platform_fee_egp), 0) AS total_platform_fees_egp,
    COUNT(*) FILTER (WHERE status = 'Completed') AS completed_transactions,
    COUNT(*) FILTER (WHERE status = 'Failed') AS failed_transactions
FROM transactions
GROUP BY DATE(created_at)
ORDER BY DATE(created_at) DESC;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_bi_daily_date
    ON mv_bi_daily_summary (date);

-- MV 2: Governorate-level statistics
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bi_governorate_stats AS
SELECT
    l.governorate,
    COUNT(DISTINCT l.land_id) AS total_lands,
    COUNT(DISTINCT l.owner_id) AS total_owners,
    COALESCE(AVG(l.price_per_sqm_egp), 0) AS avg_price_per_sqm_egp,
    COALESCE(MIN(l.price_per_sqm_egp), 0) AS min_price_per_sqm_egp,
    COALESCE(MAX(l.price_per_sqm_egp), 0) AS max_price_per_sqm_egp,
    COUNT(*) FILTER (WHERE l.status = 'Available') AS available_lands,
    COUNT(*) FILTER (WHERE l.status = 'Sold') AS sold_lands,
    COALESCE(SUM(t.amount_egp) FILTER (WHERE t.status = 'Completed'), 0) AS total_sales_egp
FROM lands l
LEFT JOIN transactions t ON t.land_id = l.land_id
GROUP BY l.governorate
ORDER BY l.governorate;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_bi_gov_gov
    ON mv_bi_governorate_stats (governorate);

-- MV 3: Broker performance summary
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bi_broker_performance AS
SELECT
    ba.broker_id,
    COALESCE(u.full_name, ba.broker_id) AS broker_name,
    COUNT(DISTINCT ba.land_id) AS lands_assigned,
    COUNT(DISTINCT ba.land_id) FILTER (WHERE ba.is_winning_broker = TRUE) AS lands_won,
    COUNT(DISTINCT ba.land_id) FILTER (WHERE ba.deals_closed > 0) AS deals_closed,
    COALESCE(SUM(ba.commission_earned_egp), 0) AS total_commission_egp,
    CASE
        WHEN COUNT(DISTINCT ba.land_id) > 0
        THEN ROUND(
            COUNT(DISTINCT ba.land_id) FILTER (WHERE ba.is_winning_broker = TRUE)::numeric
            / COUNT(DISTINCT ba.land_id) * 100, 1
        )
        ELSE 0
    END AS win_rate_pct
FROM broker_land_assignments ba
LEFT JOIN users u ON u.user_id = ba.broker_id
GROUP BY ba.broker_id, u.full_name
ORDER BY total_commission_egp DESC;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_bi_broker_id
    ON mv_bi_broker_performance (broker_id);

-- MV 4: Monthly trend for BI charts
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bi_monthly_trend AS
SELECT
    DATE_TRUNC('month', t.created_at)::DATE AS month,
    COUNT(*) AS transaction_count,
    COALESCE(SUM(t.amount_egp), 0) AS total_volume_egp,
    COALESCE(AVG(t.amount_egp), 0) AS avg_ticket_size_egp,
    COALESCE(SUM(t.platform_fee_egp), 0) AS total_fees_egp,
    COUNT(*) FILTER (WHERE t.status = 'Completed') AS completed_count
FROM transactions t
GROUP BY DATE_TRUNC('month', t.created_at)
ORDER BY month DESC;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_bi_month
    ON mv_bi_monthly_trend (month);
"""

# ──────────────────────────────────────────────
# Refresh function (scheduled daily)
# ──────────────────────────────────────────────

REFRESH_MV_SQL = """
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_bi_daily_summary;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_bi_governorate_stats;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_bi_broker_performance;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_bi_monthly_trend;
"""


async def create_indexes(session: AsyncSession) -> Dict[str, any]:
    """
    Create all performance indexes.
    Returns dict with status and count of statements executed.
    """
    statements = [s.strip() for s in INDEXES_SQL.split(';') if s.strip()]
    executed = 0
    errors = []

    for stmt in statements:
        if not stmt or stmt.startswith('--'):
            continue
        try:
            await session.execute(text(stmt))
            executed += 1
        except Exception as e:
            errors.append({"statement": stmt[:80], "error": str(e)})
            logger.warning(f"Index creation warning: {e}")

    await session.commit()

    logger.info(f"Created/verified {executed} indexes")
    return {
        "status": "partial" if errors else "success",
        "indexes_created": executed,
        "errors": errors,
    }


async def create_materialized_views(session: AsyncSession) -> Dict[str, any]:
    """
    Create all materialized views for BI Dashboard.
    """
    statements = [s.strip() for s in MATERIALIZED_VIEWS_SQL.split(';') if s.strip()]
    executed = 0
    errors = []

    for stmt in statements:
        if not stmt or stmt.startswith('--'):
            continue
        try:
            await session.execute(text(stmt))
            executed += 1
        except Exception as e:
            errors.append({"statement": stmt[:80], "error": str(e)})
            logger.warning(f"MV creation warning: {e}")

    await session.commit()

    logger.info(f"Created/verified {executed} materialized views")
    return {
        "status": "partial" if errors else "success",
        "views_created": executed,
        "errors": errors,
    }


async def refresh_materialized_views(session: AsyncSession) -> Dict[str, any]:
    """
    Refresh all materialized views CONCURRENTLY.
    Should be scheduled daily (e.g., via APScheduler or pg_cron).
    """
    statements = [s.strip() for s in REFRESH_MV_SQL.split(';') if s.strip()]
    refreshed = 0
    errors = []

    for stmt in statements:
        if not stmt or stmt.startswith('--'):
            continue
        try:
            await session.execute(text(stmt))
            refreshed += 1
        except Exception as e:
            errors.append({"statement": stmt[:80], "error": str(e)})
            logger.error(f"MV refresh error: {e}")

    await session.commit()

    return {
        "status": "partial" if errors else "success",
        "views_refreshed": refreshed,
        "errors": errors,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_bi_dashboard_data(session: AsyncSession) -> Dict[str, List]:
    """
    Fetch all BI dashboard data from materialized views.
    Fast query — no complex joins needed.
    """
    result = {}

    # Daily summary (last 30 days)
    row = await session.execute(text(
        "SELECT * FROM mv_bi_daily_summary ORDER BY date DESC LIMIT 30"
    ))
    result["daily_summary"] = [dict(r._mapping) for r in row]

    # Governorate stats
    row = await session.execute(text(
        "SELECT * FROM mv_bi_governorate_stats ORDER BY governorate"
    ))
    result["governorate_stats"] = [dict(r._mapping) for r in row]

    # Broker performance
    row = await session.execute(text(
        "SELECT * FROM mv_bi_broker_performance ORDER BY total_commission_egp DESC"
    ))
    result["broker_performance"] = [dict(r._mapping) for r in row]

    # Monthly trend (last 12 months)
    row = await session.execute(text(
        "SELECT * FROM mv_bi_monthly_trend ORDER BY month DESC LIMIT 12"
    ))
    result["monthly_trend"] = [dict(r._mapping) for r in row]

    # Summary KPIs
    row = await session.execute(text("""
        SELECT
            COALESCE(SUM(total_transactions), 0) AS total_transactions_30d,
            COALESCE(SUM(total_sales_volume_egp), 0) AS total_volume_30d,
            COALESCE(AVG(avg_transaction_value_egp), 0) AS avg_ticket_30d
        FROM mv_bi_daily_summary
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    """))
    result["kpis"] = [dict(r._mapping) for r in row]

    return result


# ──────────────────────────────────────────────
# Standalone runner (for manual execution)
# ──────────────────────────────────────────────

if __name__ == "__main__":
    """Run optimizations directly: python -m infrastructure.database.optimizations"""
    import asyncio

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/smart_land",
    )

    async def main():
        engine = create_async_engine(DATABASE_URL, echo=False)
        async with AsyncSession(engine) as session:
            print("Creating indexes...")
            idx_result = await create_indexes(session)
            print(f"  → {idx_result['indexes_created']} indexes created")

            print("Creating materialized views...")
            mv_result = await create_materialized_views(session)
            print(f"  → {mv_result['views_created']} views created")

            print("Refreshing materialized views...")
            ref_result = await refresh_materialized_views(session)
            print(f"  → {ref_result['views_refreshed']} views refreshed")

            print("Fetching BI data (test)...")
            data = await get_bi_dashboard_data(session)
            print(f"  → daily: {len(data.get('daily_summary', []))} rows")
            print(f"  → governorates: {len(data.get('governorate_stats', []))} rows")
            print(f"  → brokers: {len(data.get('broker_performance', []))} rows")
            print(f"  → monthly: {len(data.get('monthly_trend', []))} rows")

        await engine.dispose()
        print("\n✅ Database optimizations complete!")

    asyncio.run(main())