"""
Locust Load Test — نظام الإشعارات
=====================================
محاكاة 100 مستخدم يتلقون إشعارات في وقت واحد.

التشغيل:
    locust -f locustfile.py --host=http://localhost:8000

المقاييس المستهدفة:
    • P95 latency < 300ms
    • Throughput > 500 notifications/second
"""

import random

from locust import HttpUser, between, events, task

# أنواع الأحداث المتاحة
EVENT_TYPES = [
    "auction_outbid", "auction_winner", "auction_loser",
    "auction_starting", "land_match", "price_prediction",
    "wallet_deposit", "transaction_complete", "survey_reminder",
]

# بيانات تجريبية لكل نوع
PAYLOADS = {
    "auction_outbid": {
        "land_name": "أرض العاصمة الإدارية",
        "land_id": "EG-CAI-01",
        "new_bid": random.randint(5_000_000, 50_000_000),
        "auction_end": "2025-07-15T18:00:00",
    },
    "auction_winner": {
        "land_name": "أرض الإسكندرية",
        "land_id": "EG-ISK-01",
        "winning_bid": random.randint(10_000_000, 100_000_000),
    },
    "land_match": {
        "land_name": "أرض جديدة",
        "governorate": "القاهرة",
        "area_sqm": random.randint(1000, 500000),
        "price_per_sqm": random.randint(500, 10000),
        "score": random.randint(60, 99),
    },
    "wallet_deposit": {
        "amount": random.randint(1000, 100000),
        "new_balance": random.randint(50000, 500000),
    },
}


class NotificationUser(HttpUser):
    """
    محاكاة مستخدم يتلقى إشعارات.
    كل مستخدم يفعل:
        1. يطلب إشعاراته (GET)
        2. يقرأ إشعار (POST)
        3. يجلب التفضيلات (GET)
        4. يحدث التفضيلات (PUT)
    """

    # وقت الانتظار بين المهام: 0.5-2 ثانية
    wait_time = between(0.5, 2.0)

    def on_start(self):
        """تسجيل المستخدم — يُنشئ JWT token وهمي."""
        self.user_id = f"user-{self.user_index:04d}"
        self.headers = {
            "Authorization": f"Bearer stub-token-{self.user_id}",
            "Content-Type": "application/json",
        }

    @task(5)
    def get_notifications(self):
        """جلب قائمة الإشعارات (الأكثر تكراراً)."""
        self.client.get(
            "/api/notifications?limit=20",
            headers=self.headers,
            name="GET /notifications",
        )

    @task(3)
    def get_unread_count(self):
        """جلب عدد الإشعارات غير المقروءة."""
        self.client.get(
            "/api/notifications/unread-count",
            headers=self.headers,
            name="GET /unread-count",
        )

    @task(2)
    def mark_as_read(self):
        """تحديد إشعار كمقروء."""
        # نستخدم معرف وهمي — في الإنتاج يُأخذ من القائمة
        notif_id = f"notif-{self.user_index}-{random.randint(1, 100)}"
        self.client.post(
            "/api/notifications/read",
            json={"notification_id": notif_id},
            headers=self.headers,
            name="POST /read",
        )

    @task(2)
    def get_preferences(self):
        """جلب تفضيلات المستخدم."""
        self.client.get(
            "/api/notifications/preferences",
            headers=self.headers,
            name="GET /preferences",
        )

    @task(1)
    def update_preferences(self):
        """تحديث تفضيلات المستخدم."""
        channels = {
            "push": random.choice([True, False]),
            "whatsapp": random.choice([True, False]),
            "email": True,
        }
        self.client.put(
            "/api/notifications/preferences",
            json={
                "channels": channels,
                "muted_event_types": random.sample(
                    EVENT_TYPES, k=random.randint(0, 3)
                ),
            },
            headers=self.headers,
            name="PUT /preferences",
        )

    @task(3)
    def mark_all_as_read(self):
        """تحديد كل الإشعارات كمقروءة."""
        self.client.post(
            "/api/notifications/read-all",
            headers=self.headers,
            name="POST /read-all",
        )


# ── Events: طباعة تقرير الأداء ──

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """طباعة ملخص الأداء عند انتهاء الاختبار."""
    stats = environment.stats

    total_requests = stats.total.num_requests
    total_failures = stats.total.num_failures
    total_rps = stats.total.total_rps

    print("\n" + "=" * 60)
    print("  تقرير أداء نظام الإشعارات")
    print("=" * 60)
    print(f"  إجمالي الطلبات:     {total_requests:,}")
    print(f"  إجمالي الأخطاء:     {total_failures:,}")
    print(f"  نسبة النجاح:       {(1 - total_failures / max(total_requests, 1)) * 100:.1f}%")
    print(f"  Throughput (RPS):   {total_rps:.1f}")

    # التحقق من الأهداف
    p95 = getattr(stats, "aggregate_response_times_percentile", None)
    if p95:
        print(f"  P95 Latency:       {p95:.0f}ms")
        if p95 > 300:
            print("  ⚠️  P95 يتجاوز 300ms — يحتاج تحسين")
        else:
            print("  ✅ P95 ضمن الهدف (< 300ms)")

    if total_rps < 500 and total_requests > 100:
        print("  ⚠️  Throughput أقل من 500/s")
    else:
        print("  ✅ Throughput ضمن الهدف (> 500/s)")

    print("=" * 60 + "\n")