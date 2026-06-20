"""
اختبارات نظام الإشعارات
============================
تشغيل:  pytest tests/test_notifications.py -v

لا يحتاج Redis أو PostgreSQL حقيقي — يستخدم mocking.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


# ══════════════════════════════════════════════
# 1. اختبار أنواع الأحداث
# ══════════════════════════════════════════════

class TestEventTypes:
    """اختبار سجل أنواع الأحداث وتنسيق الرسائل."""

    def test_all_event_types_registered(self):
        from core.notification.event_types import EVENT_REGISTRY

        expected = [
            "auction_outbid", "auction_winner", "auction_loser",
            "auction_starting", "land_match", "price_prediction",
            "wallet_deposit", "transaction_complete", "survey_reminder",
        ]
        for et in expected:
            assert et in EVENT_REGISTRY, f"Missing event type: {et}"

    def test_format_message_success(self):
        from core.notification.event_types import get_event_type, format_message

        evt = get_event_type("auction_outbid")
        payload = {
            "land_name": "أرض العاصمة",
            "land_id": "EG-CAI-01",
            "new_bid": 10_000_000,
            "auction_end": "2025-07-15T18:00:00",
        }
        result = format_message(evt, payload)

        assert "أرض العاصمة" in result
        assert "10,000,000" in result or "10000000" in result
        assert "EG-CAI-01" in result

    def test_format_message_missing_key(self):
        from core.notification.event_types import get_event_type, format_message

        evt = get_event_type("auction_outbid")
        result = format_message(evt, {"land_name": "اختبار"})

        # يجب أن يُشير للناقص
        assert "تنسيق غير مكتمل" in result

    def test_unknown_event_type(self):
        from core.notification.event_types import get_event_type

        assert get_event_type("nonexistent_event") is None

    def test_event_priority(self):
        from core.notification.event_types import get_event_type

        outbid = get_event_type("auction_outbid")
        survey = get_event_type("survey_reminder")

        assert outbid.priority == 2  # عاجل
        assert survey.priority == 0  # عادي

    def test_event_channels(self):
        from core.notification.event_types import get_event_type, DeliveryChannel

        price_evt = get_event_type("price_prediction")
        # price_prediction لا يدعم Push ولا WhatsApp
        assert DeliveryChannel.PUSH not in price_evt.supported_channels
        assert DeliveryChannel.WHATSAPP not in price_evt.supported_channels
        assert DeliveryChannel.EMAIL in price_evt.supported_channels
        assert DeliveryChannel.IN_APP in price_evt.supported_channels


# ══════════════════════════════════════════════
# 2. اختبار النماذج
# ══════════════════════════════════════════════

class TestModels:
    """اختبار نماذج الإشعارات."""

    def test_notification_to_dict(self):
        from core.notification.models import Notification

        n = Notification(
            id="test-123",
            user_id="user-001",
            type="auction_outbid",
            title="تم تجاوز مزايدتك",
            body="تم تجاوز مزايدتك",
            data={"land_id": "EG-CAI-01"},
            priority=2,
            is_read=False,
        )
        d = n.to_dict()

        assert d["id"] == "test-123"
        assert d["user_id"] == "user-001"
        assert d["type"] == "auction_outbid"
        assert d["is_read"] is False
        assert d["priority"] == 2
        assert d["data"]["land_id"] == "EG-CAI-01"
        assert d["created_at"] is None

    def test_preference_is_channel_enabled(self):
        from core.notification.models import UserNotificationPreference

        pref = UserNotificationPreference(
            user_id="user-001",
            channels={"push": True, "whatsapp": False, "email": True},
        )

        assert pref.is_channel_enabled("push") is True
        assert pref.is_channel_enabled("whatsapp") is False
        assert pref.is_channel_enabled("email") is True
        assert pref.is_channel_enabled("sms") is False  # غير موجود

    def test_preference_is_event_muted(self):
        from core.notification.models import UserNotificationPreference

        pref = UserNotificationPreference(
            user_id="user-001",
            muted_event_types=["survey_reminder", "land_match"],
        )

        assert pref.is_event_muted("survey_reminder") is True
        assert pref.is_event_muted("land_match") is True
        assert pref.is_event_muted("auction_outbid") is False

    def test_preference_to_dict(self):
        from core.notification.models import UserNotificationPreference

        pref = UserNotificationPreference(
            user_id="user-001",
            channels={"push": True, "whatsapp": False, "email": True},
            fcm_device_token="token-abc",
            email_address="user@test.com",
        )
        d = pref.to_dict()

        assert d["user_id"] == "user-001"
        assert d["channels"]["push"] is True
        assert d["fcm_device_token"] == "token-abc"
        assert d["email_address"] == "user@test.com"


# ══════════════════════════════════════════════
# 3. اختبار NotificationService (mocked)
# ══════════════════════════════════════════════

class TestNotificationService:
    """اختبار الخدمة الرئيسية مع Redis وSession مزيفين."""

    @pytest.fixture
    def mock_redis(self):
        r = MagicMock()
        r.set = MagicMock(return_value=True)
        r.setnx = MagicMock(return_value=True)
        r.incr = MagicMock(return_value=1)
        r.expire = MagicMock()
        r.publish = MagicMock()
        r.xadd = MagicMock()
        r.sadd = MagicMock(return_value=1)
        r.smembers = MagicMock(return_value=set())
        return r

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_emit_event_success(self, mock_session, mock_redis):
        from core.notification.service import NotificationService

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

        # تحقق من استدعاء Redis
        mock_redis.set.assert_called_once()  # SETNX (dedup or throttle)

    @pytest.mark.asyncio
    async def test_emit_event_deduped(self, mock_session, mock_redis):
        from core.notification.service import NotificationService

        # SETNX يُرجع False = مكرر
        mock_redis.set = MagicMock(return_value=None)  # nx=True لم يضع

        svc = NotificationService(session=mock_session, redis=mock_redis)
        result = await svc.emit_event(
            event_type="auction_outbid",
            user_id="inv-001",
            payload={"land_id": "EG-CAI-01"},
        )

        assert result["status"] == "deduped"

    @pytest.mark.asyncio
    async def test_emit_event_unknown_type(self, mock_session, mock_redis):
        from core.notification.service import NotificationService

        svc = NotificationService(session=mock_session, redis=mock_redis)
        result = await svc.emit_event(
            event_type="nonexistent",
            user_id="inv-001",
            payload={},
        )

        assert result["status"] == "unknown_event"

    @pytest.mark.asyncio
    async def test_emit_event_throttled(self, mock_session, mock_redis):
        from core.notification.service import NotificationService

        # INCR يُرجع 6 = تجاوز الحد
        mock_redis.incr = MagicMock(return_value=6)

        svc = NotificationService(session=mock_session, redis=mock_redis)
        result = await svc.emit_event(
            event_type="survey_reminder",
            user_id="inv-001",
            payload={"service_name": "المزادات"},
        )

        assert result["status"] == "throttled"

    @pytest.mark.asyncio
    async def test_mark_as_read(self, mock_session, mock_redis):
        from core.notification.service import NotificationService
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = NotificationService(session=mock_session, redis=mock_redis)
        updated = await svc.mark_as_read("notif-123", "user-001")

        assert updated is True

    @pytest.mark.asyncio
    async def test_emit_event_no_redis(self, mock_session):
        """عند عدم توفر Redis — لا يحدث خطأ، يُخزن فقط."""
        from core.notification.service import NotificationService

        svc = NotificationService(session=mock_session, redis=None)
        result = await svc.emit_event(
            event_type="wallet_deposit",
            user_id="inv-001",
            payload={"amount": 50000, "new_balance": 100000},
        )

        assert result["status"] == "sent"
        assert "notification_id" in result


# ══════════════════════════════════════════════
# 4. اختبار قنوات الإرسال
# ══════════════════════════════════════════════

class TestDeliveryChannels:

    def test_email_service_stub(self):
        """Email يعمل في وضع Stub عند عدم تهيئة SMTP."""
        import asyncio
        from infrastructure.external.email_service import send_email

        result = asyncio.run(
            send_email("Test", "Body", "test@example.com")
        )
        assert result["success"] is True
        assert result.get("stub") is True

    def test_email_html_template(self):
        from infrastructure.external.email_service import build_notification_email_html

        html = build_notification_email_html(
            title="تم تجاوز مزايدتك",
            body="تم تجاوز مزايدتك على أرض العاصمة",
            event_type="auction_outbid",
        )

        assert "rtl" in html
        assert "تم تجاوز مزايدتك" in html
        assert "auction_outbid" in html

    def test_fcm_stub(self):
        """FCM يعمل في وضع Stub عند عدم تهيئة Firebase."""
        import asyncio
        from infrastructure.external.fcm_client import send_fcm_notification

        result = asyncio.run(
            send_fcm_notification("fake-token", "Title", "Body")
        )
        assert result["success"] is True
        assert result.get("dry_run") is True


# ══════════════════════════════════════════════
# 5. اختبار Dedup Key
# ══════════════════════════════════════════════

class TestDedupKey:

    def test_same_payload_same_key(self):
        from core.notification.service import _build_dedup_key

        k1 = _build_dedup_key("user-1", "auction_outbid", {"land_id": "EG-01"})
        k2 = _build_dedup_key("user-1", "auction_outbid", {"land_id": "EG-01"})
        assert k1 == k2

    def test_different_payload_different_key(self):
        from core.notification.service import _build_dedup_key

        k1 = _build_dedup_key("user-1", "auction_outbid", {"land_id": "EG-01"})
        k2 = _build_dedup_key("user-1", "auction_outbid", {"land_id": "EG-02"})
        assert k1 != k2

    def test_different_user_different_key(self):
        from core.notification.service import _build_dedup_key

        k1 = _build_dedup_key("user-1", "auction_outbid", {"land_id": "EG-01"})
        k2 = _build_dedup_key("user-2", "auction_outbid", {"land_id": "EG-01"})
        assert k1 != k2


# ══════════════════════════════════════════════
# 6. اختبار التكامل مع الأحداث
# ══════════════════════════════════════════════

class TestEventIntegration:

    def test_all_events_format_correctly(self):
        """كل أنواع الأحداث يجب أن تُنسّق بنجاح مع حمولات كاملة."""
        from core.notification.event_types import EVENT_REGISTRY, format_message

        payloads = {
            "auction_outbid": {
                "land_name": "أرض العاصمة", "land_id": "EG-CAI-01",
                "new_bid": 10_000_000, "auction_end": "2025-07-15T18:00:00",
            },
            "auction_winner": {
                "land_name": "أرض الإسكندرية", "land_id": "EG-ISK-01",
                "winning_bid": 20_000_000,
            },
            "auction_loser": {
                "land_name": "أرض السويس", "land_id": "EG-SUE-01",
                "final_bid": 5_000_000,
            },
            "auction_starting": {
                "land_name": "أرض 6 أكتوبر", "governorate": "الجيزة",
                "activity": "صناعي", "starting_bid": 1500,
            },
            "land_match": {
                "land_name": "أرض العاصمة", "governorate": "القاهرة",
                "area_sqm": 50000, "price_per_sqm": 3500, "score": 92,
            },
            "price_prediction": {
                "land_name": "أرض رشدي", "current_price": 5000,
                "predicted_price": 7500, "years": 3, "appreciation_pct": 50,
            },
            "wallet_deposit": {
                "amount": 50000, "new_balance": 150000,
            },
            "transaction_complete": {
                "land_name": "أرض التجمع", "land_id": "EG-CAI-02",
                "amount": 175_000_000, "tx_id": "tx-abc123",
            },
            "survey_reminder": {
                "service_name": "خدمة المزادات",
            },
        }

        for et_key, evt in EVENT_REGISTRY.items():
            payload = payloads.get(et_key, {})
            result = format_message(evt, payload)
            assert "تنسيق غير مكتمل" not in result, (
                f"Missing keys for {et_key}: need {evt.body_template_ar}"
            )