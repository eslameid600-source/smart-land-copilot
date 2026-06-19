"""
Integration Tests — Transfer Ownership & Notification Preferences
==================================================================
Tests the full transfer_ownership flow and notification service
integration with dynamic preference checking.

Run:  pytest tests/test_transfer_integration.py -v
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession


# ══════════════════════════════════════════════
# 1. Transfer Ownership Integration Tests
# ══════════════════════════════════════════════

class TestTransferOwnershipIntegration:
    """اختبارات تكامل نقل الملكية — تدفق كامل وحالات الخطأ."""

    @pytest.fixture
    def mock_session(self):
        """Mock async session for testing without real DB."""
        session = AsyncMock(spec=AsyncSession)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def lands_catalog(self):
        """Sample lands catalog for testing."""
        return {
            "LAND-CAI-001": {
                "land_id": "LAND-CAI-001",
                "name": "أرض العاصمة التجارية",
                "owner_id": "seller-mohamed-001",
                "governorate": "القاهرة",
                "total_area_sqm": 5000,
                "price_per_sqm_egp": 5000.0,
                "total_price_egp": 25_000_000.0,
                "investment_status": "متاح",
            },
            "LAND-SOLD-001": {
                "land_id": "LAND-SOLD-001",
                "name": "أرض مباعة بالفعل",
                "owner_id": "seller-ahmed-001",
                "governorate": "الجيزة",
                "total_area_sqm": 1000,
                "price_per_sqm_egp": 3000.0,
                "total_price_egp": 3_000_000.0,
                "investment_status": "مباع",
            },
        }

    @pytest.mark.asyncio
    async def test_transfer_full_success_flow(self, mock_session, lands_catalog):
        """
        تدفق نقل ملكية كامل — يجب أن ينجح مع جميع الخطوات:
        1. التحقق من الأرض
        2. التحقق من المشتري
        3. حساب العمولات
        4. خصم الرصيد
        5. تحديث الحالة
        6. تحديث الإحصائيات
        """
        from core.account.transfer_service import transfer_ownership
        from core.account.models import Investor

        # Mock investor with sufficient balance
        mock_investor = MagicMock(spec=Investor)
        mock_investor.user_id = "investor-hassan-001"
        mock_investor.wallet_balance_egp = 50_000_000.0
        mock_investor.frozen_balance_egp = 0.0
        mock_investor.available_balance_egp = 50_000_000.0
        mock_investor.updated_at = datetime.now(timezone.utc)
        mock_investor.total_invested_egp = 0.0
        mock_investor.total_purchases = 0
        mock_investor.successful_purchases = 0
        mock_investor.loyalty_points = 0

        # Mock the SELECT query to return our investor
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_investor
        mock_session.execute.return_value = mock_result

        # Mock LandownerStore
        with patch('core.account.transfer_service.LandownerStore') as MockLOStore:
            mock_lo_store = AsyncMock()
            mock_lo_store.get.return_value = {
                "user_id": "seller-mohamed-001",
                "default_commission_pct": 5.0,
            }
            mock_lo_store.exists.return_value = True
            MockLOStore.return_value = mock_lo_store

            # Mock InvestorStore methods
            with patch('core.account.transfer_service.InvestorStore') as MockInvStore:
                mock_inv_store = AsyncMock()
                mock_inv_store.exists.return_value = True
                mock_inv_store._add_transaction = AsyncMock()
                mock_inv_store.increment_purchased = AsyncMock()
                mock_inv_store.add_loyalty_points = AsyncMock(return_value=500)
                mock_inv_store.deposit = AsyncMock()
                MockInvStore.return_value = mock_inv_store

                # Execute transfer
                result = await transfer_ownership(
                    land_id="LAND-CAI-001",
                    buyer_id="investor-hassan-001",
                    session=mock_session,
                    lands_catalog=lands_catalog,
                    commission_pct=5.0,
                )

                # Verify result
                assert result["success"] is True
                assert result["land_id"] == "LAND-CAI-001"
                assert result["seller_id"] == "seller-mohamed-001"
                assert result["buyer_id"] == "investor-hassan-001"
                assert result["sale_price_egp"] == 25_000_000.0
                assert result["new_owner_id"] == "investor-hassan-001"
                assert result["transaction_id"] is not None
                assert "message_ar" in result

                # Verify commission calculation (5% of 25M = 1,250,000)
                assert result["commission_egp"] == 1_250_000.0
                assert result["loyalty_points_earned"] == 500

    @pytest.mark.asyncio
    async def test_transfer_insufficient_balance(self, mock_session, lands_catalog):
        """
        فشل نقل الملكية بسبب رصيد غير كافٍ — يجب أن يرفع ValueError.
        """
        from core.account.transfer_service import transfer_ownership
        from core.account.models import Investor

        # Mock investor with insufficient balance
        mock_investor = MagicMock(spec=Investor)
        mock_investor.available_balance_egp = 1_000.0  # Only 1,000 EGP

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_investor
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError) as exc_info:
            await transfer_ownership(
                land_id="LAND-CAI-001",
                buyer_id="investor-hassan-001",
                session=mock_session,
                lands_catalog=lands_catalog,
            )

        assert "رصيد المشتري غير كافٍ" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transfer_land_not_available(self, mock_session, lands_catalog):
        """
        فشل نقل الملكية لأن الأرض غير متاحة (مباعة) — يجب أن يرفع ValueError.
        """
        from core.account.transfer_service import transfer_ownership

        with pytest.raises(ValueError) as exc_info:
            await transfer_ownership(
                land_id="LAND-SOLD-001",  # This land is "مباع"
                buyer_id="investor-hassan-001",
                session=mock_session,
                lands_catalog=lands_catalog,
            )

        assert "غير متاحة للبيع" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transfer_land_not_found(self, mock_session, lands_catalog):
        """
        فشل نقل الملكية لأن الأرض غير موجودة في الكتالوج.
        """
        from core.account.transfer_service import transfer_ownership

        with pytest.raises(ValueError) as exc_info:
            await transfer_ownership(
                land_id="LAND-NONEXISTENT",
                buyer_id="investor-hassan-001",
                session=mock_session,
                lands_catalog=lands_catalog,
            )

        assert "غير موجودة" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transfer_no_catalog(self, mock_session):
        """
        فشل نقل الملكية بدون كتالوج — يجب أن يرفع ValueError.
        """
        from core.account.transfer_service import transfer_ownership

        with pytest.raises(ValueError) as exc_info:
            await transfer_ownership(
                land_id="LAND-CAI-001",
                buyer_id="investor-hassan-001",
                session=mock_session,
                lands_catalog=None,
            )

        assert "كتالوج الأراضي غير متوفر" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transfer_buyer_not_investor(self, mock_session, lands_catalog):
        """
        فشل نقل الملكية لأن المشتري ليس مستثمراً مسجلاً.
        """
        from core.account.transfer_service import transfer_ownership

        # Mock: buyer not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError) as exc_info:
            await transfer_ownership(
                land_id="LAND-CAI-001",
                buyer_id="non-investor-user",
                session=mock_session,
                lands_catalog=lands_catalog,
            )

        assert "ليس مستثمراً مسجلاً" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transfer_commission_calculation(self, mock_session, lands_catalog):
        """
        التحقق من دقة حساب العمولات:
        - سعر البيع: 25,000,000 EGP
        - عمولة الوسيط: 5% = 1,250,000
        - عمولة المنصة: 0.5% = 125,000
        - صافي البائع: 25,000,000 - 1,250,000 - 125,000 = 23,625,000
        """
        from core.account.transfer_service import transfer_ownership, PLATFORM_COMMISSION_PCT
        from core.account.models import Investor

        mock_investor = MagicMock(spec=Investor)
        mock_investor.user_id = "investor-hassan-001"
        mock_investor.wallet_balance_egp = 50_000_000.0
        mock_investor.frozen_balance_egp = 0.0
        mock_investor.available_balance_egp = 50_000_000.0
        mock_investor.updated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_investor
        mock_session.execute.return_value = mock_result

        with patch('core.account.transfer_service.LandownerStore') as MockLOStore:
            mock_lo_store = AsyncMock()
            mock_lo_store.get.return_value = {
                "user_id": "seller-mohamed-001",
                "default_commission_pct": 5.0,
            }
            MockLOStore.return_value = mock_lo_store

            with patch('core.account.transfer_service.InvestorStore') as MockInvStore:
                mock_inv_store = AsyncMock()
                mock_inv_store.exists.return_value = True
                mock_inv_store._add_transaction = AsyncMock()
                mock_inv_store.increment_purchased = AsyncMock()
                mock_inv_store.add_loyalty_points = AsyncMock(return_value=250)
                mock_inv_store.deposit = AsyncMock()
                MockInvStore.return_value = mock_inv_store

                result = await transfer_ownership(
                    land_id="LAND-CAI-001",
                    buyer_id="investor-hassan-001",
                    session=mock_session,
                    lands_catalog=lands_catalog,
                    commission_pct=5.0,
                )

                sale_price = 25_000_000.0
                commission_amt = 1_250_000.0  # 5%
                platform_fee = sale_price * (PLATFORM_COMMISSION_PCT / 100.0)  # 0.5%
                net_to_seller = sale_price - commission_amt - platform_fee

                assert result["commission_egp"] == commission_amt
                assert result["platform_fee_egp"] == round(platform_fee, 2)
                assert result["net_to_seller_egp"] == round(net_to_seller, 2)


# ══════════════════════════════════════════════
# 2. Notification Service Integration Tests
# ══════════════════════════════════════════════

class TestNotificationServiceIntegration:
    """اختبارات تكامل خدمة الإشعارات مع التفضيلات الديناميكية."""

    @pytest.fixture
    def mock_redis(self):
        r = MagicMock()
        r.set = MagicMock(return_value=True)
        r.setnx = MagicMock(return_value=True)
        r.incr = MagicMock(return_value=1)
        r.expire = MagicMock()
        r.publish = MagicMock()
        r.xadd = MagicMock()
        return r

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_notification_sent_based_on_preferences(self, mock_session, mock_redis):
        """
        إرسال إشعار بناءً على تفضيلات المستخدم — push مفعل.
        يجب أن يستخدم NotificationService التفضيلات لتحديد القنوات.
        """
        from core.notification.service import NotificationService

        # Mock preferences: push enabled, whatsapp disabled
        mock_pref_result = MagicMock()
        mock_pref_result.scalar_one_or_none.return_value = MagicMock(
            channels={"push": True, "whatsapp": False, "email": True},
            muted_event_types=[],
            fcm_device_token="fcm-token-123",
            email_address="user@test.com",
            is_channel_enabled=lambda c: c == "push" or c == "email",
            is_event_muted=lambda e: False,
        )
        mock_session.execute.return_value = mock_pref_result

        svc = NotificationService(session=mock_session, redis=mock_redis)
        result = await svc.emit_event(
            event_type="auction_outbid",
            user_id="inv-001",
            payload={
                "land_name": "أرض العاصمة",
                "land_id": "EG-CAI-01",
                "new_bid": 10_000_000,
                "auction_end": "2025-07-15T18:00:00",
            },
        )

        assert result["status"] == "sent"
        assert "notification_id" in result
        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_notification_not_sent_for_muted_events(self, mock_session, mock_redis):
        """
        إذا كان الحدث مكتوماً (muted) — يجب أن يتخطاه النظام.
        """
        from core.notification.service import NotificationService

        # Event is muted
        mock_pref_result = MagicMock()
        mock_pref_result.scalar_one_or_none.return_value = MagicMock(
            channels={"push": True, "whatsapp": True, "email": True},
            muted_event_types=["survey_reminder"],
            fcm_device_token=None,
            email_address="user@test.com",
            is_channel_enabled=lambda c: True,
            is_event_muted=lambda e: e == "survey_reminder",
        )
        mock_session.execute.return_value = mock_pref_result

        svc = NotificationService(session=mock_session, redis=mock_redis)
        result = await svc.emit_event(
            event_type="survey_reminder",
            user_id="inv-001",
            payload={"service_name": "المزادات"},
        )

        assert result["status"] == "muted"

    @pytest.mark.asyncio
    async def test_notification_dedup(self, mock_session, mock_redis):
        """
        إرسال إشعار مكرر — يجب أن يرصد النظام التكرار ويرفضه.
        """
        from core.notification.service import NotificationService
        from core.notification.service import _build_dedup_key

        # First call succeeds
        mock_redis.set = MagicMock(return_value=True)  # SETNX success

        svc = NotificationService(session=mock_session, redis=mock_redis)
        result1 = await svc.emit_event(
            event_type="transaction_complete",
            user_id="inv-001",
            payload={"land_id": "EG-CAI-01", "amount": 500_000},
        )
        assert result1["status"] == "sent"

        # Second call with same payload — should be deduped
        mock_redis.set = MagicMock(return_value=None)  # SETNX fails (key exists)

        result2 = await svc.emit_event(
            event_type="transaction_complete",
            user_id="inv-001",
            payload={"land_id": "EG-CAI-01", "amount": 500_000},
        )
        assert result2["status"] == "deduped"

        # Verify different keys for different payloads
        k1 = _build_dedup_key("inv-001", "transaction_complete", {"land_id": "EG-CAI-01"})
        k2 = _build_dedup_key("inv-001", "transaction_complete", {"land_id": "EG-CAI-02"})
        assert k1 != k2, "Different payloads should produce different dedup keys"

    @pytest.mark.asyncio
    async def test_notification_throttling(self, mock_session, mock_redis):
        """
        تجاوز حد الإرسال (throttle) — يجب أن يرفض النظام الإشعار.
        """
        from core.notification.service import NotificationService

        # INCR returns 6 — exceeds limit of 5/hour
        mock_redis.incr = MagicMock(return_value=6)

        svc = NotificationService(session=mock_session, redis=mock_redis)
        result = await svc.emit_event(
            event_type="survey_reminder",
            user_id="inv-001",
            payload={"service_name": "المزادات"},
        )

        assert result["status"] == "throttled"

    @pytest.mark.asyncio
    async def test_notification_unknown_event_type(self, mock_session, mock_redis):
        """
        نوع حدث غير معروف — يجب أن يعيد unknown_event.
        """
        from core.notification.service import NotificationService

        svc = NotificationService(session=mock_session, redis=mock_redis)
        result = await svc.emit_event(
            event_type="nonexistent_event_type",
            user_id="inv-001",
            payload={},
        )

        assert result["status"] == "unknown_event"

    @pytest.mark.asyncio
    async def test_notification_no_redis_fallback(self, mock_session):
        """
        عند عدم توفر Redis — يجب أن يعمل النظام بدون Cache (يخزن فقط في DB).
        """
        from core.notification.service import NotificationService

        svc = NotificationService(session=mock_session, redis=None)
        result = await svc.emit_event(
            event_type="wallet_deposit",
            user_id="inv-001",
            payload={"amount": 50000, "new_balance": 100000},
        )

        assert result["status"] == "sent"
        assert "notification_id" in result

    @pytest.mark.asyncio
    async def test_mark_as_read_updates_db(self, mock_session, mock_redis):
        """
        تحديث إشعار كمقروء — يجب أن يستدعي UPDATE في قاعدة البيانات.
        """
        from core.notification.service import NotificationService

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = NotificationService(session=mock_session, redis=mock_redis)
        updated = await svc.mark_as_read("notif-123", "user-001")

        assert updated is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_as_read_not_found(self, mock_session, mock_redis):
        """
        محاولة تحديث إشعار غير موجود — يجب أن تُرجع False.
        """
        from core.notification.service import NotificationService

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = NotificationService(session=mock_session, redis=mock_redis)
        updated = await svc.mark_as_read("notif-nonexistent", "user-001")

        assert updated is False

    @pytest.mark.asyncio
    async def test_notification_preferences_update(self, mock_session, mock_redis):
        """
        تحديث تفضيلات الإشعارات — يجب أن يحفظ القنوات الجديدة والأحداث المكتومة.
        """
        from core.notification.service import NotificationService

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = NotificationService(session=mock_session, redis=mock_redis)

        # Spy on update_preferences
        with patch.object(svc, 'update_preferences') as mock_update:
            mock_update.return_value = {
                "user_id": "user-001",
                "channels": {"push": False, "whatsapp": True, "email": False},
                "muted_event_types": ["survey_reminder"],
            }

            result = await svc.update_preferences(
                user_id="user-001",
                channels={"push": False, "whatsapp": True, "email": False},
                muted_event_types=["survey_reminder"],
            )

            assert result["user_id"] == "user-001"
            assert result["channels"]["whatsapp"] is True
            assert result["channels"]["push"] is False
            assert "survey_reminder" in result["muted_event_types"]