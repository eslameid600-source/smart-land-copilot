"""Alembic env.py — بيئة الترحيل (Migration Environment)
==========================================================
يستخدم النماذج من core.account.models لإنشاء ترحيلات تلقائية.
يعمل مع PostgreSQL عبر asyncpg.

الاستخدام:
    alembic revision --autogenerate -m "create account tables"
    alembic upgrade head
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ─── إضافة مسار المشروع ───
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ─── استيراد النماذج (ضروري لـ autogenerate) ───
from core.account.models import Base  # noqa: E402, F401
from core.auction.models import Auction, Bid  # noqa: E402, F401
from core.notification.models import Notification  # noqa: E402, F401
from payment.models import IdempotencyKey  # noqa: E402, F401

# ─── إعدادات Alembic ───
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ─── تعيين target_metadata ───
# Alembic يستخدم هذا لمعرفة الجداول عند --autogenerate
target_metadata = Base.metadata

# ─── تجاوز sqlalchemy.url من متغير البيئة ───
database_url = os.getenv("DATABASE_URL", "")
if database_url:
    # تحويل postgresql:// إلى postgresql+asyncpg://
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    config.set_main_option("sqlalchemy.url", database_url)


# ─── دوال التشغيل (async) ───

def run_migrations_offline() -> None:
    """
    تشغيل الترحيلات في 'offline' mode.

    يُنشئ فقط SQL بدون تنفيذه — مفيد للمراجعة.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # ترجمة أسماء الأعمدة العربية
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """تنفيذ الترحيلات عبر اتصال حقيقي."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    تشغيل الترحيلات في 'online' mode مع asyncpg.

    ينشئ محرك async ويُنفذ الترحيلات.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """نقطة الدخول لـ online mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()