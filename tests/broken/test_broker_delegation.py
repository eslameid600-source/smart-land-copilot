"""
Unit Tests — Broker Delegation Service
=========================================
Tests the dual-broker allocation, Winner-Takes-Commission rule,
and performance tracking logic.

Run:  pytest tests/test_broker_delegation.py -v
"""

import pytest
from datetime import datetime
from decimal import Decimal

from api.routes.broker_delegation_service import BrokerDelegationService


# ──────────────────────────────────────────────
# Sample data
# ──────────────────────────────────────────────

LAND_ID = "EG-CAI-TEST-001"
LAND_ID_2 = "EG-CAI-TEST-002"
BROKER_A = "broker-ali-001"
BROKER_B = "broker-omar-002"
BROKER_C = "broker-sara-003"
BUYER_ID = "investor-hassan-001"

LAND_NAMES = {
    LAND_ID: "أرض العاصمة التجريبية",
    LAND_ID_2: "أرض الشيخ زايد",
}

BROKER_NAMES = {
    BROKER_A: "علي محمد",
    BROKER_B: "عمر حسن",
    BROKER_C: "سارة أحمد",
}


# ══════════════════════════════════════════════
# 1. Allocation Tests
# ══════════════════════════════════════════════

class TestAllocation:
    """اختبارات تخصيص الوسطاء للأراضي."""

    def test_allocate_first_broker(self):
        """تعيين وسيط أول لأرض — يجب أن ينجح."""
        svc = BrokerDelegationService()
        alloc, err = svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        assert err == ""
        assert alloc is not None
        assert alloc.broker_id == BROKER_A
        assert alloc.broker_name == BROKER_NAMES[BROKER_A]
        assert alloc.is_winning_broker is False

        # تحقق من وجوده
        brokers = svc.get_land_brokers(LAND_ID)
        assert len(brokers) == 1

    def test_allocate_second_broker(self):
        """تعيين وسيط ثانٍ — يجب أن ينجح (الحد الأقصى 2)."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        alloc, err = svc.allocate_broker(LAND_ID, BROKER_B, BROKER_NAMES[BROKER_B])

        assert err == ""
        assert alloc is not None
        assert alloc.broker_id == BROKER_B

        brokers = svc.get_land_brokers(LAND_ID)
        assert len(brokers) == 2

    def test_allocate_third_broker_rejected(self):
        """تعيين وسيط ثالث — يجب أن يُرفض (حد أقصى 2)."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        svc.allocate_broker(LAND_ID, BROKER_B, BROKER_NAMES[BROKER_B])
        alloc, err = svc.allocate_broker(LAND_ID, BROKER_C, BROKER_NAMES[BROKER_C])

        assert alloc is None
        assert "Maximum 2 brokers" in err
        assert BROKER_A in err

    def test_allocate_duplicate_broker_rejected(self):
        """تعيين نفس الوسيط مرتين — يجب أن يُرفض."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        alloc, err = svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        assert alloc is None
        assert "already allocated" in err

    def test_allocate_different_lands(self):
        """نفس الوسيط يمكن تعيينه لأراضٍ مختلفة."""
        svc = BrokerDelegationService()
        alloc1, _ = svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        alloc2, _ = svc.allocate_broker(LAND_ID_2, BROKER_A, BROKER_NAMES[BROKER_A])

        assert alloc1 is not None
        assert alloc2 is not None
        assert len(svc.get_land_brokers(LAND_ID)) == 1
        assert len(svc.get_land_brokers(LAND_ID_2)) == 1


# ══════════════════════════════════════════════
# 2. Removal Tests
# ══════════════════════════════════════════════

class TestRemoval:
    """اختبارات إزالة الوسطاء."""

    def test_remove_existing_broker(self):
        """إزالة وسيط موجود — يجب أن تنجح."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        svc.allocate_broker(LAND_ID, BROKER_B, BROKER_NAMES[BROKER_B])

        removed = svc.remove_broker(LAND_ID, BROKER_A)
        assert removed is True

        brokers = svc.get_land_brokers(LAND_ID)
        assert len(brokers) == 1
        assert brokers[0].broker_id == BROKER_B

    def test_remove_nonexistent_broker(self):
        """إزالة وسيط غير موجود — يجب أن تُرجع False."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        removed = svc.remove_broker(LAND_ID, "nonexistent-broker")
        assert removed is False

    def test_remove_from_empty_land(self):
        """إزالة من أرض ليس بها وسطاء — يجب أن تُرجع False."""
        svc = BrokerDelegationService()
        removed = svc.remove_broker(LAND_ID, BROKER_A)
        assert removed is False


# ══════════════════════════════════════════════
# 3. Lead Tracking Tests
# ══════════════════════════════════════════════

class TestLeadTracking:
    """اختبارات تتبع العملاء المحتملين."""

    def test_record_lead_increments(self):
        """تسجيل عميل محتمل — يجب أن يزيد العداد."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        svc.record_broker_lead(LAND_ID, BROKER_A)
        svc.record_broker_lead(LAND_ID, BROKER_A)

        brokers = svc.get_land_brokers(LAND_ID)
        assert brokers[0].leads_generated == 2

    def test_record_lead_multiple_brokers(self):
        """تسجيل عملاء لوسطاء مختلفين."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        svc.allocate_broker(LAND_ID, BROKER_B, BROKER_NAMES[BROKER_B])

        svc.record_broker_lead(LAND_ID, BROKER_A)
        svc.record_broker_lead(LAND_ID, BROKER_A)
        svc.record_broker_lead(LAND_ID, BROKER_B)

        brokers = svc.get_land_brokers(LAND_ID)
        leads_a = next(b.leads_generated for b in brokers if b.broker_id == BROKER_A)
        leads_b = next(b.leads_generated for b in brokers if b.broker_id == BROKER_B)
        assert leads_a == 2
        assert leads_b == 1


# ══════════════════════════════════════════════
# 4. Winner-Takes-Commission Tests
# ══════════════════════════════════════════════

class TestCloseDeal:
    """اختبارات إغلاق الصفقة وحساب العمولات — Winner-Takes-Commission Rule."""

    TRANSACTION_VALUE = 500_000.00  # 500,000 EGP
    COMMISSION_PCT = 5.0  # 5%

    def test_winning_broker_gets_full_commission(self):
        """الوسيط الفائز يحصل على العمولة كاملة (5% من 500,000 = 25,000)."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        svc.allocate_broker(LAND_ID, BROKER_B, BROKER_NAMES[BROKER_B])

        record = svc.close_deal(
            land_id=LAND_ID,
            winning_broker_id=BROKER_A,
            buyer_id=BUYER_ID,
            transaction_value_egp=self.TRANSACTION_VALUE,
            broker_commission_pct=self.COMMISSION_PCT,
        )

        assert record is not None
        expected_commission = self.TRANSACTION_VALUE * (self.COMMISSION_PCT / 100)
        assert record.winning_broker_commission_egp == expected_commission
        assert record.winning_broker_id == BROKER_A
        assert record.deal_closed is True

    def test_secondary_broker_gets_zero(self):
        """الوسيط الثاني (غير الفائز) يحصل على 0 جنيه عمولة."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        svc.allocate_broker(LAND_ID, BROKER_B, BROKER_NAMES[BROKER_B])

        record = svc.close_deal(
            land_id=LAND_ID,
            winning_broker_id=BROKER_A,
            buyer_id=BUYER_ID,
            transaction_value_egp=self.TRANSACTION_VALUE,
            broker_commission_pct=self.COMMISSION_PCT,
        )

        assert record.secondary_broker_commission_egp == 0.0
        assert record.secondary_broker_id == BROKER_B

    def test_commission_calculation_accuracy(self):
        """التحقق من دقة حساب العمولة: 100,000 * 5% = 5,000."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        value = 100_000.00
        commission_pct = 5.0

        record = svc.close_deal(
            land_id=LAND_ID,
            winning_broker_id=BROKER_A,
            buyer_id=BUYER_ID,
            transaction_value_egp=value,
            broker_commission_pct=commission_pct,
        )

        assert record.winning_broker_commission_egp == 5_000.00
        assert record.transaction_value_egp == 100_000.00
        assert record.broker_commission_pct == 5.0

    def test_commission_various_rates(self):
        """اختبار نسب عمولة مختلفة: 1.5%, 3%, 7.5%."""
        svc = BrokerDelegationService()

        test_cases = [
            (1_000_000.00, 1.5, 15_000.00),    # 1.5% من 1M
            (200_000.00, 3.0, 6_000.00),        # 3% من 200K
            (50_000.00, 7.5, 3_750.00),          # 7.5% من 50K
        ]

        for i, (value, pct, expected) in enumerate(test_cases):
            land_id = f"{LAND_ID}-{i}"
            svc.allocate_broker(land_id, BROKER_A, BROKER_NAMES[BROKER_A])
            record = svc.close_deal(
                land_id=land_id,
                winning_broker_id=BROKER_A,
                buyer_id=BUYER_ID,
                transaction_value_egp=value,
                broker_commission_pct=pct,
            )
            assert record.winning_broker_commission_egp == expected, (
                f"Failed for {pct}% of {value}: expected {expected}, got {record.winning_broker_commission_egp}"
            )

    def test_deal_updates_broker_metrics(self):
        """إغلاق الصفقة يزيد counters الوسيط (deals_closed, commission_earned)."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        svc.close_deal(
            land_id=LAND_ID,
            winning_broker_id=BROKER_A,
            buyer_id=BUYER_ID,
            transaction_value_egp=200_000.00,
            broker_commission_pct=5.0,
        )

        brokers = svc.get_land_brokers(LAND_ID)
        winner = brokers[0]
        assert winner.deals_closed == 1
        assert winner.commission_earned_egp == 10_000.00  # 5% of 200K
        assert winner.is_winning_broker is True

    def test_get_commission_record(self):
        """استرجاع سجل العمولة لصفقة مغلقة."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        svc.close_deal(
            land_id=LAND_ID,
            winning_broker_id=BROKER_A,
            buyer_id=BUYER_ID,
            transaction_value_egp=300_000.00,
            broker_commission_pct=4.0,
        )

        record = svc.get_commission_record(LAND_ID)
        assert record is not None
        assert record.land_id == LAND_ID
        assert record.buyer_id == BUYER_ID

    def test_commission_record_nonexistent(self):
        """استرجاع سجل لصفقة غير موجودة."""
        svc = BrokerDelegationService()
        record = svc.get_commission_record("nonexistent-land")
        assert record is None

    def test_get_all_commission_records(self):
        """استرجاع كل سجلات العمولات."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, "")
        svc.allocate_broker(LAND_ID_2, BROKER_B, "")

        svc.close_deal(LAND_ID, BROKER_A, BUYER_ID, 100_000.00, 5.0)
        svc.close_deal(LAND_ID_2, BROKER_B, BUYER_ID, 200_000.00, 3.0)

        records = svc.get_all_commission_records()
        assert len(records) == 2


# ══════════════════════════════════════════════
# 5. Performance Summary Tests
# ══════════════════════════════════════════════

class TestPerformanceSummary:
    """اختبارات ملخص أداء الوسيط."""

    def test_empty_performance(self):
        """وسيط لم يقم بأي نشاط — جميع القيم صفر."""
        svc = BrokerDelegationService()
        summary = svc.get_broker_performance_summary(BROKER_A)

        assert summary["broker_id"] == BROKER_A
        assert summary["lands_assigned"] == 0
        assert summary["total_leads_generated"] == 0
        assert summary["total_deals_closed"] == 0
        assert summary["total_commission_earned_egp"] == 0.0
        assert summary["win_rate_pct"] == 0.0

    def test_performance_after_leads_and_deals(self):
        """حساب الأداء بعد عملاء وصفقات."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        svc.allocate_broker(LAND_ID_2, BROKER_A, BROKER_NAMES[BROKER_A])

        # 3 leads on first land, 1 on second
        svc.record_broker_lead(LAND_ID, BROKER_A)
        svc.record_broker_lead(LAND_ID, BROKER_A)
        svc.record_broker_lead(LAND_ID, BROKER_A)
        svc.record_broker_lead(LAND_ID_2, BROKER_A)

        # Close one deal (winning)
        svc.close_deal(LAND_ID, BROKER_A, BUYER_ID, 500_000.00, 5.0)

        summary = svc.get_broker_performance_summary(BROKER_A)

        assert summary["lands_assigned"] == 2
        assert summary["total_leads_generated"] == 4
        assert summary["total_deals_closed"] == 1
        assert summary["total_commission_earned_egp"] == 25_000.00  # 5% of 500K
        assert summary["win_rate_pct"] == 50.0  # 1 won out of 2

    def test_performance_multiple_brokers(self):
        """كل وسيط له أداء مستقل."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])
        svc.allocate_broker(LAND_ID, BROKER_B, BROKER_NAMES[BROKER_B])
        svc.allocate_broker(LAND_ID_2, BROKER_B, BROKER_NAMES[BROKER_B])

        svc.record_broker_lead(LAND_ID, BROKER_A)
        svc.record_broker_lead(LAND_ID, BROKER_B)
        svc.record_broker_lead(LAND_ID_2, BROKER_B)

        svc.close_deal(LAND_ID, BROKER_A, BUYER_ID, 100_000.00, 5.0)

        summary_a = svc.get_broker_performance_summary(BROKER_A)
        summary_b = svc.get_broker_performance_summary(BROKER_B)

        # Broker A: 1 land, 1 lead, 1 deal won, 5K commission
        assert summary_a["lands_assigned"] == 1
        assert summary_a["total_leads_generated"] == 1
        assert summary_a["total_deals_closed"] == 1
        assert summary_a["total_commission_earned_egp"] == 5_000.00
        assert summary_a["win_rate_pct"] == 100.0

        # Broker B: 2 lands, 2 leads, 0 deals, 0 commission
        assert summary_b["lands_assigned"] == 2
        assert summary_b["total_leads_generated"] == 2
        assert summary_b["total_deals_closed"] == 0
        assert summary_b["total_commission_earned_egp"] == 0.0
        assert summary_b["win_rate_pct"] == 0.0


# ══════════════════════════════════════════════
# 6. Edge Cases
# ══════════════════════════════════════════════

class TestEdgeCases:
    """اختبارات الحالات الحدودية."""

    def test_close_deal_with_single_broker(self):
        """إغلاق صفقة بوسيط واحد فقط — يجب أن ينجح (الثاني = None)."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        record = svc.close_deal(LAND_ID, BROKER_A, BUYER_ID, 100_000.00, 3.0)

        assert record is not None
        assert record.winning_broker_id == BROKER_A
        assert record.secondary_broker_id is None
        assert record.winning_broker_commission_egp == 3_000.00

    def test_close_deal_without_allocation(self):
        """محاولة إغلاق صفقة لأرض بدون وسطاء — يجب أن ينجز (لكن بدون فائز)."""
        svc = BrokerDelegationService()
        record = svc.close_deal(LAND_ID, BROKER_A, BUYER_ID, 100_000.00, 5.0)

        assert record is not None
        # Winning broker didn't have allocation — still processes
        assert record.transaction_value_egp == 100_000.00

    def test_zero_commission_rate(self):
        """نسبة عمولة 0% — يجب أن تكون العمولة 0."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        record = svc.close_deal(LAND_ID, BROKER_A, BUYER_ID, 1_000_000.00, 0.0)

        assert record.winning_broker_commission_egp == 0.0

    def test_very_high_transaction_value(self):
        """قيمة معاملة عالية جداً (1B EGP) — يجب ألا يحدث تجاوز."""
        svc = BrokerDelegationService()
        svc.allocate_broker(LAND_ID, BROKER_A, BROKER_NAMES[BROKER_A])

        record = svc.close_deal(LAND_ID, BROKER_A, BUYER_ID, 1_000_000_000.00, 2.5)

        assert record.winning_broker_commission_egp == 25_000_000.0  # 2.5% of 1B