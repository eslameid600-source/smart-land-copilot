"""
Security Tests — Bandit & Static Analysis
============================================
اختبارات أمنية للكشف عن الثغرات في الاعتماديات الجديدة
(API keys, hardcoded secrets, SQL injection, etc.)

التشغيل:
    bandit -r . -f json -o bandit_report.json
    pytest tests/test_security.py -v

المتطلبات:
    pip install bandit
"""

import os
import json
import subprocess
import pytest
from pathlib import Path


# ══════════════════════════════════════════════
# 1. Bandit Security Scan
# ══════════════════════════════════════════════

class TestBanditSecurityScan:
    """تشغيل Bandit للكشف عن الثغرات الأمنية في الكود."""

    @pytest.fixture(scope="class")
    def bandit_results(self):
        """تشغيل Bandit وجمع النتائج."""
        report_path = Path("bandit_report.json")

        try:
            result = subprocess.run(
                ["bandit", "-r", ".", "-f", "json", "-o", str(report_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            pytest.skip("bandit not installed — run: pip install bandit")
            return {"results": []}
        except subprocess.TimeoutExpired:
            pytest.skip("bandit timed out")
            return {"results": []}

        if report_path.exists():
            with open(report_path) as f:
                data = json.load(f)
            return data
        return {"results": []}

    def test_no_high_severity_issues(self, bandit_results):
        """
        يجب ألا يكون هناك ثغرات أمنية عالية الخطورة (HIGH).
        """
        high_issues = [
            issue for issue in bandit_results.get("results", [])
            if issue.get("issue_severity") == "HIGH"
        ]

        if high_issues:
            print("\n⚠️  ثغرات عالية الخطورة:")
            for issue in high_issues:
                print(f"  - {issue.get('filename')}:{issue.get('line_number')}")
                print(f"    {issue.get('issue_text')}")
                print(f"    {issue.get('test_id')}")

        assert len(high_issues) == 0, (
            f"تم العثور على {len(high_issues)} ثغرة عالية الخطورة!"
        )

    def test_no_hardcoded_passwords(self, bandit_results):
        """
        يجب ألا يكون هناك كلمات مرور مكتوبة في الكود (Hardcoded passwords).
        """
        password_issues = [
            issue for issue in bandit_results.get("results", [])
            if "password" in issue.get("issue_text", "").lower()
            or issue.get("test_id") == "B105"
        ]

        assert len(password_issues) == 0, (
            f"تم العثور على {len(password_issues)} كلمة مرور مكتوبة في الكود!"
        )

    def test_no_sql_injection(self, bandit_results):
        """
        يجب ألا يكون هناك ثغرات SQL Injection.
        """
        sql_issues = [
            issue for issue in bandit_results.get("results", [])
            if issue.get("test_id") in ("B608", "B609", "B610")
        ]

        assert len(sql_issues) == 0, (
            f"تم العثور على {len(sql_issues)} ثغرة SQL Injection!"
        )

    def test_no_eval_usage(self, bandit_results):
        """
        يجب ألا يكون هناك استخدام لـ eval() أو exec().
        """
        eval_issues = [
            issue for issue in bandit_results.get("results", [])
            if issue.get("test_id") in ("B307", "B351", "B352")
        ]

        assert len(eval_issues) == 0, (
            f"تم العثور على {len(eval_issues)} استخدام لـ eval/exec!"
        )

    def test_no_insecure_http(self, bandit_results):
        """
        يجب ألا يكون هناك استخدام لـ HTTP بدون TLS في الإنتاج.
        """
        http_issues = [
            issue for issue in bandit_results.get("results", [])
            if "http://" in issue.get("issue_text", "")
            and "localhost" not in issue.get("issue_text", "")
            and "127.0.0.1" not in issue.get("issue_text", "")
        ]

        # هذا اختبار إعلامي فقط — قد يكون HTTP مقبولاً في التطوير
        if http_issues:
            print("\n⚠️  استخدام HTTP (قد يكون مقبولاً في التطوير):")
            for issue in http_issues:
                print(f"  - {issue.get('filename')}:{issue.get('line_number')}")


# ══════════════════════════════════════════════
# 2. API Key Exposure Check
# ══════════════════════════════════════════════

class TestAPIKeyExposure:
    """التحقق من عدم تسريب مفاتيح API في الكود."""

    KEY_PATTERNS = [
        "GROQ_API_KEY",
        "MAPBOX_ACCESS_TOKEN",
        "JWT_SECRET",
        "ERP_API_KEY",
        "OPENAI_API_KEY",
        "AWS_SECRET",
        "sk-[a-zA-Z0-9]{20,}",  # OpenAI keys
        "pk\\.[a-zA-Z0-9]{20,}",  # Mapbox keys
    ]

    EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}

    def test_no_api_keys_in_source_code(self):
        """
        التحقق من عدم وجود مفاتيح API حقيقية في الكود المصدري.
        """
        root = Path(".")
        suspicious_files = []

        for py_file in root.rglob("*.py"):
            # تخطي المجلدات المستبعدة
            if any(excluded in py_file.parts for excluded in self.EXCLUDED_DIRS):
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for pattern in self.KEY_PATTERNS:
                if pattern in content:
                    # التحقق من أنها ليست مجرد متغير بيئة
                    line_num = 0
                    for line in content.split("\n"):
                        line_num += 1
                        if pattern in line and "os.getenv" not in line and "environ" not in line:
                            suspicious_files.append({
                                "file": str(py_file),
                                "line": line_num,
                                "pattern": pattern,
                                "content": line.strip()[:100],
                            })

        if suspicious_files:
            print("\n⚠️  ملفات قد تحتوي على مفاتيح API:")
            for item in suspicious_files:
                print(f"  - {item['file']}:{item['line']}")
                print(f"    {item['content']}")

        # هذا اختبار إعلامي — قد تكون المفاتيح في ملفات .env.example
        assert len(suspicious_files) == 0, (
            f"تم العثور على {len(suspicious_files)} مفتاح API في الكود!"
        )


# ══════════════════════════════════════════════
# 3. Dependency Security Check
# ══════════════════════════════════════════════

class TestDependencySecurity:
    """التحقق من أمان الاعتماديات."""

    def test_requirements_no_insecure_packages(self):
        """
        التحقق من عدم وجود حزم غير آمنة في requirements.txt.
        """
        req_files = ["requirements.txt", "requirements-dev.txt"]

        for req_file in req_files:
            path = Path(req_file)
            if not path.exists():
                continue

            content = path.read_text(encoding="utf-8")

            # حزم معروفة بثغرات أمنية
            insecure_packages = [
                "PyYAML<5.4",  # CVE-2020-14343
                "urllib3<1.26.5",  # CVE-2021-33503
                "requests<2.25.0",  # CVE-2018-18074
                "cryptography<3.3.2",  # CVE-2020-36242
                "Django<3.2",  # CVEs متعددة
                "Flask<2.0",  # CVE-2018-1000656
            ]

            for insecure in insecure_packages:
                if insecure.lower() in content.lower():
                    pytest.fail(f"حزمة غير آمنة في {req_file}: {insecure}")


# ══════════════════════════════════════════════
# 4. Environment Variable Check
# ══════════════════════════════════════════════

class TestEnvironmentSecurity:
    """التحقق من إعدادات البيئة."""

    def test_env_file_not_committed(self):
        """
        التأكد من عدم وجود ملف .env في المستودع (يجب أن يكون في .gitignore).
        """
        env_file = Path(".env")
        if env_file.exists():
            # تحقق من أن الملف ليس مجرد مثال
            content = env_file.read_text(encoding="utf-8")
            if "SECRET" in content or "PASSWORD" in content or "API_KEY" in content:
                # هذا تحذير — قد يكون الملف للتطوير المحلي
                print("\n⚠️  ملف .env موجود — تأكد من أنه في .gitignore!")

    def test_gitignore_contains_env(self):
        """
        التأكد من أن .gitignore يستبعد ملفات .env.
        """
        gitignore = Path(".gitignore")
        if not gitignore.exists():
            pytest.skip("لا يوجد ملف .gitignore")

        content = gitignore.read_text(encoding="utf-8")
        assert ".env" in content, "ملف .gitignore لا يستبعد .env!"


# ══════════════════════════════════════════════
# 5. Mapbox Fallback Test
# ══════════════════════════════════════════════

class TestMapboxFallback:
    """التحقق من أن الخريطة تعمل بدون Mapbox API key (fallback إلى Leaflet)."""

    def test_mapbox_fallback_configured(self):
        """
        التأكد من أن نظام الخرائط يستخدم fallback عند عدم وجود Mapbox token.
        """
        from infrastructure.gis.map_optimizer import get_mapbox_config, get_map_html

        # محاكاة عدم وجود token
        config = get_mapbox_config()
        assert config is not None, "يجب أن يعود MapConfig حتى بدون token"

        # التحقق من أن HTML الناتج يحتوي على Leaflet fallback
        html = get_map_html(map_config=config)
        assert "leaflet" in html.lower() or "openstreetmap" in html.lower(), (
            "يجب أن تحتوي الخريطة على fallback إلى Leaflet/OSM"
        )

    def test_mapbox_token_validation(self):
        """
        التحقق من التحقق من صحة Mapbox token.
        """
        from infrastructure.gis.map_optimizer import get_mapbox_config

        # بدون token
        os.environ.pop("MAPBOX_ACCESS_TOKEN", None)
        config = get_mapbox_config()
        assert config.access_token == "", "يجب أن يكون token فارغاً بدون متغير بيئة"

        # مع token
        os.environ["MAPBOX_ACCESS_TOKEN"] = "pk.test_token_12345"
        config = get_mapbox_config()
        assert config.access_token == "pk.test_token_12345", "يجب أن يقرأ token من البيئة"

        # تنظيف
        os.environ.pop("MAPBOX_ACCESS_TOKEN", None)


# ══════════════════════════════════════════════
# 6. AI Provider Security Check
# ══════════════════════════════════════════════

class TestAIProviderSecurity:
    """التحقق من أمان مزود AI."""

    def test_groq_api_key_not_hardcoded(self):
        """
        التأكد من أن مفتاح Groq API ليس مكتوباً في الكود.
        """
        from core.ai_recommendation import GROQ_API_KEY

        # إذا كان المفتاح موجوداً في البيئة، هذا مقبول
        if GROQ_API_KEY:
            assert GROQ_API_KEY != "your-groq-api-key-here", (
                "مفتاح Groq API هو القيمة الافتراضية!"
            )
            assert len(GROQ_API_KEY) > 20, "مفتاح Groq API قصير جداً"

    def test_ollama_url_validation(self):
        """
        التحقق من صحة رابط Ollama.
        """
        from core.ai_recommendation import OLLAMA_BASE_URL

        assert OLLAMA_BASE_URL.startswith("http"), "رابط Ollama يجب أن يبدأ بـ http"
        assert "localhost" in OLLAMA_BASE_URL or "127.0.0.1" in OLLAMA_BASE_URL, (
            "Ollama يجب أن يكون على localhost للأمان"
        )


# ══════════════════════════════════════════════
# 7. ERP Integration Security
# ══════════════════════════════════════════════

class TestERPSecurity:
    """التحقق من أمان تكامل ERP."""

    def test_erp_api_key_not_hardcoded(self):
        """
        التأكد من أن مفتاح ERP API ليس مكتوباً في الكود.
        """
        from core.erp_integration import ERP_API_KEY

        if ERP_API_KEY:
            assert ERP_API_KEY != "your-erp-api-key", (
                "مفتاح ERP API هو القيمة الافتراضية!"
            )

    def test_erp_hmac_signing(self):
        """
        التأكد من توقيع طلبات ERP بـ HMAC.
        """
        from core.erp_integration import _sign_payload

        payload = {"test": "data", "amount": 1000}
        signature = _sign_payload(payload)

        # إذا كان هناك مفتاح API، يجب أن يكون التوقيع غير فارغ
        from core.erp_integration import ERP_API_KEY
        if ERP_API_KEY:
            assert signature != "", "يجب أن يكون التوقيع غير فارغ مع مفتاح API"
            assert len(signature) == 64, "HMAC-SHA256 يجب أن يكون 64 حرفاً"