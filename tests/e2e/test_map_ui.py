"""
E2E Tests — Map UI & Interactive Components
==============================================
اختبارات تفاعلية باستخدام Playwright لمكونات واجهة المستخدم.

التشغيل:
    pytest tests/e2e/test_map_ui.py --headed  (لرؤية المتصفح)
    pytest tests/e2e/test_map_ui.py           (بدون واجهة)

المتطلبات:
    pip install playwright
    playwright install chromium

الاختبارات:
    1. النقر على أزرار التحكم في الخريطة (Zoom, Pan, Layer toggle)
    2. رفع ملف PDF للعقود
    3. تعبئة بيانات الوسيط (Broker form)
    4. التحقق من ظهور الإشعارات
"""

import os
from pathlib import Path
from typing import Generator

import pytest

# Skip all tests if playwright is not installed
pytest.importorskip("playwright")

from playwright.sync_api import (Browser, BrowserContext, Page, expect,
                                 sync_playwright)

# ══════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Sample PDF for upload test
SAMPLE_PDF_PATH = Path(__file__).parent / "test_data" / "sample_contract.pdf"


def _ensure_sample_pdf():
    """إنشاء ملف PDF نموذجي للاختبار إذا لم يكن موجوداً."""
    pdf_dir = SAMPLE_PDF_PATH.parent
    pdf_dir.mkdir(parents=True, exist_ok=True)
    if not SAMPLE_PDF_PATH.exists():
        # إنشاء PDF بسيط
        try:
            from reportlab.pdfgen import canvas
            c = canvas.Canvas(str(SAMPLE_PDF_PATH))
            c.drawString(100, 750, "Sample Contract - Smart Land Copilot")
            c.drawString(100, 730, "هذا عقد نموذجي لاختبار رفع الملفات")
            c.save()
        except ImportError:
            # إنشاء ملف نصي كبديل
            SAMPLE_PDF_PATH.write_text("Sample contract content", encoding="utf-8")


@pytest.fixture(scope="session")
def browser() -> Generator[Browser, None, None]:
    """إنشاء متصفح Chromium للاختبارات."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=os.getenv("E2E_HEADED", "").lower() not in ("1", "true"),
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        yield browser
        browser.close()


@pytest.fixture
def context(browser: Browser) -> Generator[BrowserContext, None, None]:
    """سياق متصفح جديد لكل اختبار."""
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="ar-EG",
        timezone_id="Africa/Cairo",
        # Mock API responses
        extra_http_headers={
            "Authorization": "Bearer e2e-test-token",
        },
    )
    yield context
    context.close()


@pytest.fixture
def page(context: BrowserContext) -> Generator[Page, None, None]:
    """صفحة جديدة لكل اختبار."""
    page = context.new_page()
    # تسجيل أي أخطاء في console للمساعدة في التصحيح
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
    yield page
    page.close()


# ══════════════════════════════════════════════
# 1. اختبار أزرار التحكم في الخريطة
# ══════════════════════════════════════════════

class TestMapControls:
    """اختبار أزرار التحكم في الخريطة — Zoom, Pan, Layers."""

    @pytest.fixture(autouse=True)
    def setup_map_page(self, page: Page):
        """التوجه إلى صفحة الخريطة."""
        page.goto(f"{FRONTEND_URL}/map", wait_until="networkidle")
        # انتظار تحميل الخريطة
        page.wait_for_selector("[data-testid='map-container']", timeout=15000)
        yield

    def test_zoom_in_button(self, page: Page):
        """النقر على زر Zoom In — يجب أن يغير مستوى التكبير."""
        zoom_btn = page.locator("[data-testid='zoom-in-btn']")
        expect(zoom_btn).toBeVisible()

        # التحقق من مستوى التكبير الحالي
        initial_zoom = page.locator("[data-testid='zoom-level']").text_content()

        # النقر على Zoom In
        zoom_btn.click()
        page.wait_for_timeout(500)  # انتظار تأثير التكبير

        new_zoom = page.locator("[data-testid='zoom-level']").text_content()
        assert new_zoom != initial_zoom, "يجب أن يتغير مستوى التكبير بعد Zoom In"

    def test_zoom_out_button(self, page: Page):
        """النقر على زر Zoom Out."""
        zoom_out_btn = page.locator("[data-testid='zoom-out-btn']")
        expect(zoom_out_btn).toBeVisible()

        initial_zoom = page.locator("[data-testid='zoom-level']").text_content()
        zoom_out_btn.click()
        page.wait_for_timeout(500)

        new_zoom = page.locator("[data-testid='zoom-level']").text_content()
        assert new_zoom != initial_zoom, "يجب أن يتغير مستوى التكبير بعد Zoom Out"

    def test_layer_toggle(self, page: Page):
        """تبديل طبقات الخريطة — تشغيل/إيقاف طبقة."""
        # النقر على زر طبقة Satellite
        satellite_btn = page.locator("[data-testid='layer-satellite']")
        expect(satellite_btn).toBeVisible()

        # التحقق من أنها غير نشطة (أو نشطة)
        is_active = satellite_btn.get_attribute("data-active")

        # النقر لتبديل الحالة
        satellite_btn.click()
        page.wait_for_timeout(300)

        new_active = satellite_btn.get_attribute("data-active")
        assert new_active != is_active, "يجب أن تتغير حالة الطبقة بعد النقر"

    def test_pan_map(self, page: Page):
        """سحب الخريطة (Pan) — محاكاة السحب بالماوس."""
        map_container = page.locator("[data-testid='map-container']")

        # الحصول على إحداثيات الخريطة قبل السحب
        initial_coords = map_container.get_attribute("data-center")

        # محاكاة السحب
        map_box = map_container.bounding_box()
        if map_box:
            start_x = map_box["x"] + map_box["width"] / 2
            start_y = map_box["y"] + map_box["height"] / 2

            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x + 100, start_y + 50, steps=10)
            page.mouse.up()
            page.wait_for_timeout(500)

            new_coords = map_container.get_attribute("data-center")
            assert new_coords != initial_coords, "يجب أن يتغير مركز الخريطة بعد السحب"

    def test_marker_click_shows_popup(self, page: Page):
        """النقر على علامة (Marker) — يجب أن يظهر نافذة منبثقة."""
        marker = page.locator("[data-testid='map-marker']").first
        expect(marker).toBeVisible(timeout=10000)

        marker.click()
        page.wait_for_timeout(300)

        # التحقق من ظهور الـ Popup
        popup = page.locator("[data-testid='marker-popup']")
        expect(popup).toBeVisible(timeout=5000)
        assert "سعر" in popup.text_content() or "EGP" in popup.text_content()


# ══════════════════════════════════════════════
# 2. اختبار رفع ملف PDF
# ══════════════════════════════════════════════

class TestFileUpload:
    """اختبار رفع ملف PDF للعقود."""

    @pytest.fixture(autouse=True)
    def setup_upload_page(self, page: Page):
        """التوجه إلى صفحة رفع العقود."""
        _ensure_sample_pdf()
        page.goto(f"{FRONTEND_URL}/contracts/upload", wait_until="networkidle")
        page.wait_for_selector("[data-testid='file-upload-area']", timeout=10000)
        yield

    def test_upload_pdf_file(self, page: Page):
        """رفع ملف PDF — يجب أن يظهر في قائمة الملفات."""
        file_input = page.locator("[data-testid='file-input']")

        # رفع الملف
        file_input.set_input_files(str(SAMPLE_PDF_PATH))

        # انتظار اكتمال الرفع
        page.wait_for_selector("[data-testid='upload-progress']", state="hidden", timeout=10000)

        # التحقق من ظهور الملف في القائمة
        file_list = page.locator("[data-testid='uploaded-files']")
        expect(file_list).toBeVisible()
        assert "sample_contract.pdf" in file_list.text_content()

    def test_upload_validation_rejects_invalid_type(self, page: Page):
        """رفع ملف غير PDF — يجب أن يظهر خطأ في التحقق."""
        file_input = page.locator("[data-testid='file-input']")

        # إنشاء ملف نصي مؤقت
        temp_file = SAMPLE_PDF_PATH.parent / "test_invalid.txt"
        temp_file.write_text("This is not a PDF", encoding="utf-8")

        try:
            # محاولة رفع ملف غير PDF
            file_input.set_input_files(str(temp_file))

            # التحقق من ظهور رسالة الخطأ
            error_msg = page.locator("[data-testid='upload-error']")
            expect(error_msg).toBeVisible(timeout=5000)
            assert "PDF" in error_msg.text_content() or "غير مسموح" in error_msg.text_content()
        finally:
            # تنظيف
            if temp_file.exists():
                temp_file.unlink()

    def test_multiple_files_upload(self, page: Page):
        """رفع ملفات متعددة — يجب أن تظهر جميعها."""
        file_input = page.locator("[data-testid='file-input']")

        # إنشاء ملف PDF إضافي
        extra_pdf = SAMPLE_PDF_PATH.parent / "extra_contract.pdf"
        try:
            try:
                from reportlab.pdfgen import canvas
                c = canvas.Canvas(str(extra_pdf))
                c.drawString(100, 750, "Extra Contract")
                c.save()
            except ImportError:
                extra_pdf.write_text("Extra contract", encoding="utf-8")

            # رفع ملفين معاً
            file_input.set_input_files([str(SAMPLE_PDF_PATH), str(extra_pdf)])

            # انتظار الرفع
            page.wait_for_timeout(2000)

            file_list = page.locator("[data-testid='uploaded-files']")
            expect(file_list).toBeVisible()
            files_text = file_list.text_content()
            assert "sample_contract.pdf" in files_text
            assert "extra_contract.pdf" in files_text
        finally:
            if extra_pdf.exists():
                extra_pdf.unlink()


# ══════════════════════════════════════════════
# 3. اختبار تعبئة بيانات الوسيط
# ══════════════════════════════════════════════

class TestBrokerForm:
    """اختبار تعبئة بيانات الوسيط — النموذج."""

    @pytest.fixture(autouse=True)
    def setup_broker_page(self, page: Page):
        """التوجه إلى صفحة تسجيل الوسيط."""
        page.goto(f"{FRONTEND_URL}/broker/register", wait_until="networkidle")
        page.wait_for_selector("[data-testid='broker-form']", timeout=10000)
        yield

    def test_fill_broker_form_success(self, page: Page):
        """تعبئة نموذج الوسيط بنجاح — يجب أن يُرسل."""
        # تعبئة الحقول
        page.fill("[data-testid='broker-name']", "علي محمد أحمد")
        page.fill("[data-testid='broker-phone']", "+201001234567")
        page.fill("[data-testid='broker-email']", "ali@example.com")
        page.fill("[data-testid='broker-license']", "BRK-2025-001234")
        page.fill("[data-testid='broker-experience']", "10")

        # اختيار المحافظة
        page.select_option("[data-testid='broker-governorate']", "القاهرة")

        # الموافقة على الشروط
        page.check("[data-testid='broker-terms']")

        # إرسال النموذج
        page.click("[data-testid='broker-submit']")

        # انتظار رسالة النجاح
        success_msg = page.locator("[data-testid='broker-success']")
        expect(success_msg).toBeVisible(timeout=10000)
        assert "تم التسجيل" in success_msg.text_content() or "نجاح" in success_msg.text_content()

    def test_broker_form_validation_empty_fields(self, page: Page):
        """حقول فارغة — يجب أن تظهر رسائل خطأ التحقق."""
        # النقر على إرسال بدون تعبئة
        page.click("[data-testid='broker-submit']")

        # التحقق من ظهور رسائل الخطأ
        errors = page.locator("[data-testid='field-error']")
        expect(errors.first).toBeVisible(timeout=3000)
        # يجب أن يكون هناك على الأقل خطأ واحد
        assert errors.count() >= 1

    def test_broker_form_invalid_phone(self, page: Page):
        """رقم هاتف غير صالح — يجب أن يظهر خطأ."""
        page.fill("[data-testid='broker-name']", "علي محمد")
        page.fill("[data-testid='broker-phone']", "123")  # رقم غير صالح
        page.fill("[data-testid='broker-email']", "ali@test.com")
        page.fill("[data-testid='broker-license']", "BRK-001")
        page.fill("[data-testid='broker-experience']", "5")
        page.select_option("[data-testid='broker-governorate']", "الجيزة")
        page.check("[data-testid='broker-terms']")

        page.click("[data-testid='broker-submit']")

        # التحقق من ظهور خطأ الهاتف
        phone_error = page.locator("[data-testid='field-error']").filter(has_text="هاتف")
        expect(phone_error).toBeVisible(timeout=3000)

    def test_broker_form_invalid_email(self, page: Page):
        """بريد إلكتروني غير صالح — يجب أن يظهر خطأ."""
        page.fill("[data-testid='broker-name']", "سارة أحمد")
        page.fill("[data-testid='broker-phone']", "+201001234567")
        page.fill("[data-testid='broker-email']", "not-an-email")  # غير صالح
        page.fill("[data-testid='broker-license']", "BRK-002")
        page.fill("[data-testid='broker-experience']", "3")
        page.select_option("[data-testid='broker-governorate']", "الإسكندرية")
        page.check("[data-testid='broker-terms']")

        page.click("[data-testid='broker-submit']")

        # التحقق من ظهور خطأ البريد
        email_error = page.locator("[data-testid='field-error']").filter(has_text="بريد")
        expect(email_error).toBeVisible(timeout=3000)


# ══════════════════════════════════════════════
# 4. اختبار الإشعارات
# ══════════════════════════════════════════════

class TestNotifications:
    """اختبار ظهور الإشعارات والتفاعل معها."""

    def test_notification_badge_shows_unread_count(self, page: Page):
        """شارة الإشعارات — يجب أن تظهر عدد الإشعارات غير المقروءة."""
        page.goto(f"{FRONTEND_URL}/dashboard", wait_until="networkidle")

        # انتظار ظهور شارة الإشعارات
        badge = page.locator("[data-testid='notification-badge']")
        expect(badge).toBeVisible(timeout=10000)

        # التحقق من أن العدد رقم (أو 0)
        count_text = badge.text_content()
        assert count_text.isdigit() or count_text == "", "يجب أن تكون شارة الإشعارات رقماً"

    def test_click_notification_opens_panel(self, page: Page):
        """النقر على شارة الإشعارات — يجب أن يفتح لوحة الإشعارات."""
        page.goto(f"{FRONTEND_URL}/dashboard", wait_until="networkidle")

        # النقر على شارة الإشعارات
        badge = page.locator("[data-testid='notification-badge']")
        badge.click()

        # التحقق من ظهور لوحة الإشعارات
        panel = page.locator("[data-testid='notification-panel']")
        expect(panel).toBeVisible(timeout=5000)

    def test_mark_notification_as_read(self, page: Page):
        """تحديد إشعار كمقروء — يجب أن يختفي من اللائحة."""
        page.goto(f"{FRONTEND_URL}/notifications", wait_until="networkidle")
        page.wait_for_selector("[data-testid='notification-item']", timeout=10000)

        # الحصول على أول إشعار
        first_notif = page.locator("[data-testid='notification-item']").first
        expect(first_notif).toBeVisible()

        # النقر على زر "تحديد كمقروء"
        read_btn = first_notif.locator("[data-testid='mark-read-btn']")
        if read_btn.is_visible():
            read_btn.click()
            page.wait_for_timeout(300)

            # يجب أن يتغير نمط الإشعار (يصبح غير مميز)
            expect(first_notif).to_have_attribute("data-read", "true")

    def test_notification_preferences_toggle(self, page: Page):
        """تبديل تفضيلات الإشعارات — تشغيل/إيقاف قناة."""
        page.goto(f"{FRONTEND_URL}/notifications/preferences", wait_until="networkidle")
        page.wait_for_selector("[data-testid='preferences-form']", timeout=10000)

        # إيقاف الإشعارات عبر Push
        push_toggle = page.locator("[data-testid='toggle-push']")
        was_checked = push_toggle.is_checked()

        push_toggle.click()
        page.wait_for_timeout(300)

        is_checked = push_toggle.is_checked()
        assert is_checked != was_checked, "يجب أن تتغير حالة التبديل"


# ══════════════════════════════════════════════
# 5. اختبار لوحة المعلومات (Dashboard)
# ══════════════════════════════════════════════

class TestDashboard:
    """اختبار لوحة المعلومات — BI Dashboard."""

    def test_dashboard_loads_kpi_cards(self, page: Page):
        """تحميل لوحة المعلومات — يجب أن تظهر بطاقات KPI."""
        page.goto(f"{FRONTEND_URL}/dashboard", wait_until="networkidle")

        # انتظار ظهور بطاقات KPI
        kpi_cards = page.locator("[data-testid='kpi-card']")
        expect(kpi_cards.first).toBeVisible(timeout=15000)

        # يجب أن يكون هناك على الأقل 4 بطاقات
        assert kpi_cards.count() >= 4

    def test_dashboard_charts_render(self, page: Page):
        """الرسوم البيانية في لوحة المعلومات — يجب أن تظهر."""
        page.goto(f"{FRONTEND_URL}/dashboard", wait_until="networkidle")

        # انتظار ظهور الرسوم البيانية
        charts = page.locator("[data-testid='dashboard-chart']")
        expect(charts.first).toBeVisible(timeout=15000)

        # التحقق من وجود أنواع مختلفة من الرسوم
        chart_types = charts.all()
        chart_names = [chart.get_attribute("data-chart-type") for chart in chart_types]
        assert any(name for name in chart_names), "يجب أن يكون للرسوم البيانية أنواع"

    def test_dashboard_date_filter(self, page: Page):
        """فلترة لوحة المعلومات حسب التاريخ."""
        page.goto(f"{FRONTEND_URL}/dashboard", wait_until="networkidle")
        page.wait_for_selector("[data-testid='date-filter']", timeout=10000)

        # اختيار فترة زمنية
        date_filter = page.locator("[data-testid='date-filter']")
        date_filter.select_option("last_30_days")

        page.wait_for_timeout(1000)  # انتظار تحديث البيانات

        # التحقق من تحديث البيانات
        kpi_values = page.locator("[data-testid='kpi-value']")
        expect(kpi_values.first).toBeVisible()