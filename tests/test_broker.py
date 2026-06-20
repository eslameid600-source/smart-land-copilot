"""
اختبارات نظام الوسطاء
======================
اختبارات وحدة وتكامل تغطي:
- تسجيل وسيط
- تعيين وسيط لأرض
- حساب العمولة
- البحث عن وسطاء
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from unittest.mock import AsyncMock, MagicMock

from core.account.models import Base, Broker, BrokerAssignment, BrokerTransaction, BrokerStatus
from core.account.broker_repository import BrokerRepository
from core.account.broker_service import BrokerService


# ──────────────────────────────────────────
# إعداد قاعدة بيانات اختبار (SQLite في الذاكرة)
# ──────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session():
    """إنشاء جلسة قاعدة بيانات اختبار."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    
    await engine.dispose()


@pytest.fixture
def broker_repo(db_session):
    return BrokerRepository(db_session)


@pytest.fixture
def broker_service(db_session):
    return BrokerService(db_session)


# ──────────────────────────────────────────
# اختبارات تسجيل وسيط
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_broker(broker_repo: BrokerRepository):
    """تسجيل وسيط جديد."""
    broker = await broker_repo.create(
        user_id="user-broker-001",
        full_name="أحمد محمد",
        phone_number="01012345678",
        email="ahmed@example.com",
        default_commission_rate=5.0,
    )
    
    assert broker["user_id"] == "user-broker-001"
    assert broker["full_name"] == "أحمد محمد"
    assert broker["default_commission_rate"] == 5.0
    assert broker["status"] == "inactive"
    assert broker["broker_code"].startswith("BRK-")
    assert len(broker["broker_code"]) == 12  # BRK- + 8 characters = 12 total


@pytest.mark.asyncio
async def test_register_broker_invalid_commission(broker_repo):
    """رفض نسبة عمولة Outside النطاق."""
    with pytest.raises(ValueError, match="بين 1% و 20%"):
        await broker_repo.create(
            user_id="user-broker-002",
            full_name=" Jessica",
            default_commission_rate=25.0,
        )


@pytest.mark.asyncio
async def test_register_duplicate_broker(broker_repo):
    """منع تسجيل وسيط مرتين."""
    await broker_repo.create(
        user_id="user-broker-003",
        full_name="كريم علي",
    )
    with pytest.raises(ValueError, match="مسجل كوسيط مسبقاً"):
        await broker_repo.create(
            user_id="user-broker-003",
            full_name="كريم علي 2",
        )


# ──────────────────────────────────────────
# اختبارات الاسترجاع والتحديث
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_broker(broker_repo):
    """استرجاع بيانات وسيط."""
    created = await broker_repo.create(
        user_id="user-broker-004",
        full_name="سارة أحمد",
    )
    broker_id = created["id"]
    
    fetched = await broker_repo.get(broker_id)
    assert fetched is not None
    assert fetched["id"] == broker_id
    assert fetched["full_name"] == "سارة أحمد"


@pytest.mark.asyncio
async def test_update_commission_rate(broker_repo):
    """تحديث نسبة العمولة."""
    created = await broker_repo.create(
        user_id="user-broker-005",
        full_name="محمد حسن",
        default_commission_rate=3.0,
    )
    
    updated = await broker_repo.update_commission_rate(created["id"], 7.5)
    assert updated["default_commission_rate"] == 7.5


@pytest.mark.asyncio
async def test_update_commission_rate_out_of_range(broker_repo):
    """رفع خطأ عند تحديث نسبة عمولة خارج النطاق."""
    created = await broker_repo.create(
        user_id="user-broker-006",
        full_name="نور Diana",
    )
    
    with pytest.raises(ValueError, match="بين 1% و 20%"):
        await broker_repo.update_commission_rate(created["id"], 0.5)


# ──────────────────────────────────────────
# اختبارات التعيينات
# ──────────────────────────────────────────

@pytest_asyncio.fixture
async def broker_with_land(broker_repo):
    """إنشاء وسيط نشط ومعتمد + أرض للاختبارات."""
    broker = await broker_repo.create(
        user_id="broker-land-001",
        full_name="وسيط تجريبي",
        default_commission_rate=4.0,
    )
    # تفعيل الوسيط وتأكيد التحقق
    await broker_repo.update_status(broker["id"], "active")
    await broker_repo.verify_broker(broker["id"], True)
    # إعادة الجلب
    return await broker_repo.get(broker["id"])


@pytest.mark.asyncio
async def test_assign_broker_to_land(broker_repo, broker_with_land):
    """تعيين وسيط لأرض."""
    assignment = await broker_repo.assign_broker(
        land_id="LAND-001",
        broker_id=broker_with_land["id"],
        commission_percent=5.0,
    )
    
    assert assignment["land_id"] == "LAND-001"
    assert assignment["broker_id"] == broker_with_land["id"]
    assert assignment["commission_percent"] == 5.0
    assert assignment["status"] == "active"


@pytest.mark.asyncio
async def test_assign_broker_already_assigned(broker_repo, broker_with_land):
    """رفض تعيين وسيط لأرض مُخصصة مسبقاً."""
    await broker_repo.assign_broker(
        land_id="LAND-002",
        broker_id=broker_with_land["id"],
    )
    
    with pytest.raises(ValueError, match="تعيين نشط مسبقاً"):
        await broker_repo.assign_broker(
            land_id="LAND-002",
            broker_id=broker_with_land["id"],
        )


# ──────────────────────────────────────────
# اختبارات البحث
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_active_brokers(broker_repo):
    """البحث عن وسطاء نشطين."""
    # إنشاء عدة وسطاء وتفعيلهم
    b1 = await broker_repo.create(user_id="search-1", full_name="بحث واحد")
    b2 = await broker_repo.create(user_id="search-2", full_name="بحث اثنان", specialization=["سكني"])
    for b in [b1, b2]:
        await broker_repo.update_status(b["id"], "active")
        await broker_repo.verify_broker(b["id"], True)
    
    results = await broker_repo.search(query="بحث", limit=10)
    assert len(results) >= 1


# ──────────────────────────────────────────
# اختبارات معاملات العمولات
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_broker_transaction(broker_repo, broker_with_land):
    """إنشاء معاملة عمولة."""
    tx = await broker_repo.add_transaction(
        broker_id=broker_with_land["id"],
        transaction_id="tx-001",
        land_id="LAND-001",
        sale_amount_egp=1000000,
        commission_rate_pct=5.0,
    )
    
    assert tx["sale_amount_egp"] == 1000000
    assert tx["commission_rate_pct"] == 5.0
    assert tx["commission_amount_egp"] == 50000.0
    assert tx["status"] == "pending"


@pytest.mark.asyncio
async def test_mark_transaction_paid(broker_repo, broker_with_land):
    """تحديث حالة المعاملة إلى مدفوعة."""
    tx = await broker_repo.add_transaction(
        broker_id=broker_with_land["id"],
        transaction_id="tx-002",
        land_id="LAND-001",
        sale_amount_egp=500000,
        commission_rate_pct=4.0,
    )
    
    paid = await broker_repo.mark_transaction_paid(tx["id"])
    assert paid["status"] == "paid"
    assert paid["paid_at"] is not None


@pytest.mark.asyncio
async def test_get_broker_earnings(broker_repo, broker_with_land):
    """حساب أرباح الوسيط."""
    await broker_repo.add_transaction(
        broker_id=broker_with_land["id"],
        transaction_id="tx-earn-1",
        land_id="LAND-001",
        sale_amount_egp=1000000,
        commission_rate_pct=5.0,
    )
    
    earnings = await broker_repo.get_broker_earnings(broker_with_land["id"])
    assert earnings["transactions_count"] == 1
    assert earnings["total_pending_egp"] > 0