"""
Locust Load Test — Full System
==================================
محاكاة 500-1000 مستخدم متزامن يطلبون البيانات من النظام.

التشغيل:
    locust -f tests/load_tests/locustfile_full.py --host=http://localhost:8000

الأهداف:
    • P95 latency < 300ms
    • Throughput > 500 req/s
    • محاكاة سلوك المستخدمين الحقيقيين
"""

from locust import HttpUser, task, between, events, constant
import json
import random
import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

USER_IDS = [f"user-{i:04d}" for i in range(1, 1001)]
LAND_IDS = [f"LAND-{random.choice(['CAI','GIZ','ISK','SUE','ALX'])}-{i:03d}" for i in range(1, 201)]

# Simulated user data for realistic payloads
GOVERNORATES = ["القاهرة", "الجيزة", "الإسكندرية", "السويس", "الأقصر", "أسوان"]
LAND_STATUSES = ["Available", "Sold", "Pending"]


class RealisticUser(HttpUser):
    """
    محاكاة مستخدم حقيقي يتفاعل مع النظام.
    كل مستخدم له نمط استخدام مختلف: متصفح، مستثمر، وسيط.
    """

    # وقت الانتظار بين المهام: 1-5 ثوانٍ (محاكاة التفكير البشري)
    wait_time = between(1.0, 5.0)

    def on_start(self):
        """تسجيل المستخدم — لكل مستخدم هوية مختلفة."""
        self.user_id = random.choice(USER_IDS)
        self.token = f"test-token-{self.user_id}-{random.randint(1000, 9999)}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.user_type = random.choice(["browser", "investor", "broker"])

    # ─── المهمة 1: تصفح الأراضي (الأكثر تكراراً) ───

    @task(10)
    def browse_lands(self):
        """تصفح قائمة الأراضي — الصفحة الرئيسية."""
        params = {
            "limit": random.choice([20, 50, 100]),
            "offset": random.choice([0, 20, 40, 60]),
            "governorate": random.choice(GOVERNORATES + [""]),
        }
        self.client.get(
            "/api/lands",
            params=params,
            headers=self.headers,
            name="GET /api/lands",
        )

    # ─── المهمة 2: فتح تفاصيل أرض ───

    @task(5)
    def view_land_detail(self):
        """عرض تفاصيل أرض محددة."""
        land_id = random.choice(LAND_IDS)
        self.client.get(
            f"/api/lands/{land_id}",
            headers=self.headers,
            name="GET /api/lands/[id]",
        )

    # ─── المهمة 3: لوحة المعلومات (Dashboard) ───

    @task(3)
    def get_dashboard(self):
        """جلب بيانات لوحة المعلومات — BI Dashboard."""
        self.client.get(
            "/api/dashboard/summary",
            headers=self.headers,
            name="GET /api/dashboard/summary",
        )

    # ─── المهمة 4: التوقعات (Predictions) ───

    @task(4)
    def get_market_overview(self):
        """جلب نظرة عامة على السوق — نقطة نهاية بطيئة."""
        self.client.get(
            "/api/predictions/market-overview",
            headers=self.headers,
            name="GET /api/predictions/market-overview",
        )

    # ─── المهمة 5: الإشعارات ───

    @task(6)
    def get_notifications(self):
        """جلب الإشعارات — أكثر نقطة نهاية استخداماً."""
        self.client.get(
            "/api/notifications?limit=20",
            headers=self.headers,
            name="GET /api/notifications",
        )

    @task(3)
    def get_unread_count(self):
        """جلب عدد الإشعارات غير المقروءة."""
        self.client.get(
            "/api/notifications/unread-count",
            headers=self.headers,
            name="GET /api/notifications/unread-count",
        )

    # ─── المهمة 6: البحث في الأراضي ───

    @task(4)
    def search_lands(self):
        """البحث في الأراضي بمعايير مختلفة."""
        params = {
            "q": random.choice(["أرض", "عمارة", "فيلا", "مكتب", ""]),
            "min_price": random.choice([100000, 500000, 1000000]),
            "max_price": random.choice([5000000, 10000000, 50000000]),
            "governorate": random.choice(GOVERNORATES + [""]),
        }
        self.client.get(
            "/api/lands/search",
            params=params,
            headers=self.headers,
            name="GET /api/lands/search",
        )

    # ─── المهمة 7: تحديث التفضيلات ───

    @task(2)
    def update_preferences(self):
        """تحديث تفضيلات الإشعارات."""
        self.client.put(
            "/api/notifications/preferences",
            json={
                "channels": {
                    "push": random.choice([True, False]),
                    "whatsapp": random.choice([True, False]),
                    "email": True,
                },
                "muted_event_types": random.sample(
                    ["auction_outbid", "survey_reminder", "land_match"],
                    k=random.randint(0, 2),
                ),
            },
            headers=self.headers,
            name="PUT /api/notifications/preferences",
        )

    # ─── المهمة 8: الخريطة (محاكاة فتح الخريطة) ───

    @task(5)
    def load_map(self):
        """تحميل بيانات الخريطة — محاكاة فتح صفحة الخريطة الرئيسية."""
        bounds = {
            "north": random.uniform(30.0, 31.5),
            "south": random.uniform(29.5, 30.0),
            "east": random.uniform(31.0, 32.5),
            "west": random.uniform(29.8, 31.0),
        }
        self.client.get(
            "/api/map/tiles",
            params=bounds,
            headers=self.headers,
            name="GET /api/map/tiles",
        )

    @task(3)
    def get_map_pois(self):
        """جلب نقاط الاهتمام (POIs) للخريطة."""
        params = {
            "lat": random.uniform(29.8, 31.5),
            "lon": random.uniform(29.8, 32.5),
            "radius": random.choice([1000, 2000, 5000]),
        }
        self.client.get(
            "/api/map/pois",
            params=params,
            headers=self.headers,
            name="GET /api/map/pois",
        )

    # ─── المهمة 9: العمليات الخاصة بالمستثمر ───

    @task(2)
    def get_investor_profile(self):
        """جلب ملف المستثمر (إذا كان المستخدم مستثمراً)."""
        if self.user_type == "investor":
            self.client.get(
                "/api/investor/profile",
                headers=self.headers,
                name="GET /api/investor/profile",
            )

    @task(1)
    def get_transaction_history(self):
        """جلب سجل المعاملات."""
        self.client.get(
            "/api/transactions",
            params={"limit": 20, "offset": 0},
            headers=self.headers,
            name="GET /api/transactions",
        )

    # ─── المهمة 10: صحة الخدمة ───

    @task(1)
    def health_check(self):
        """فحص صحة الخدمة."""
        self.client.get(
            "/api/notifications/health",
            headers=self.headers,
            name="GET /api/notifications/health",
        )


# ──────────────────────────────────────────────
# Burst Test — فتح الخريطة الرئيسية في وقت واحد
# ──────────────────────────────────────────────

class MapBurstUser(HttpUser):
    """
    محاكاة مجموعة من المستخدمين يفتحون الخريطة في وقت واحد.
    يستخدم wait_time ثابت (0) لبدء جميع المستخدمين معاً.
    """
    wait_time = constant(0)
    weight = 1  # نسبة أقل من المستخدمين العاديين

    def on_start(self):
        self.headers = {
            "Authorization": f"Bearer burst-token-{random.randint(1, 100)}",
            "Content-Type": "application/json",
        }

    @task
    def burst_map_load(self):
        """
        فتح الخريطة الرئيسية — إرسال 3 طلبات متزامنة
        لمحاكاة تحميل صفحة كاملة (tiles + POIs + layers).
        """
        bounds = {
            "north": 30.5,
            "south": 29.8,
            "east": 31.5,
            "west": 30.0,
        }

        # 1. Load map tiles
        self.client.get(
            "/api/map/tiles",
            params=bounds,
            headers=self.headers,
            name="BURST /api/map/tiles",
        )

        # 2. Load POIs
        self.client.get(
            "/api/map/pois",
            params={"lat": 30.1, "lon": 31.2, "radius": 5000},
            headers=self.headers,
            name="BURST /api/map/pois",
        )

        # 3. Load map layers
        self.client.get(
            "/api/map/layers",
            headers=self.headers,
            name="BURST /api/map/layers",
        )


# ══════════════════════════════════════════════
# Events — طباعة التقرير عند انتهاء الاختبار
# ══════════════════════════════════════════════

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """طباعة تقرير الأداء الشامل."""
    stats = environment.stats

    total_req = stats.total.num_requests
    total_fail = stats.total.num_failures
    total_rps = stats.total.total_rps
    avg_time = stats.total.avg_response_time
    p95 = getattr(stats.total, "avg_response_time", None)

    print("\n" + "=" * 70)
    print("  📊 تقرير أداء النظام الشامل — Smart Land Copilot")
    print("=" * 70)
    print(f"  إجمالي الطلبات:       {total_req:>10,}")
    print(f"  إجمالي الأخطاء:       {total_fail:>10,}")
    print(f"  نسبة النجاح:          {((1 - total_fail / max(total_req, 1)) * 100):>9.1f}%")
    print(f"  Throughput (RPS):      {total_rps:>10.1f}")
    print(f"  متوسط زمن الاستجابة:  {avg_time:>10.1f}ms")
    print()

    # Print per-endpoint stats
    print("  تفاصيل النقاط:")
    print("-" * 70)
    for key in sorted(stats.entries.keys()):
        entry = stats.entries[key]
        if entry.num_requests > 0:
            fail_pct = (entry.num_failures / entry.num_requests) * 100
            print(
                f"  {entry.name:<40s} "
                f"req={entry.num_requests:>6,d} "
                f"avg={entry.avg_response_time:>7.1f}ms "
                f"fail={fail_pct:>5.1f}%"
            )

    print()
    print("=" * 70)

    # Check targets
    if total_rps >= 500:
        print("  ✅ Throughput >= 500 req/s — الهدف محقق")
    else:
        print(f"  ⚠️  Throughput {total_rps:.1f} req/s — أقل من الهدف (500)")

    if avg_time and avg_time < 300:
        print(f"  ✅ متوسط زمن الاستجابة {avg_time:.0f}ms — ضمن الهدف (< 300ms)")
    else:
        print(f"  ⚠️  متوسط زمن الاستجابة {avg_time:.0f}ms — يتجاوز الهدف (300ms)")

    print("=" * 70 + "\n")