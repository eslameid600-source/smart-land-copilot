#!/usr/bin/env python3
"""
refactor_imports.py — سكربت تحديث مسارات الاستيراد تلقائياً
==============================================================
Smart Land Management Copilot — Clean Architecture Import Refactorer
=====================================================================

يقرأ جميع ملفات .py في المشروع ويُحدّث مسارات الاستيراد
من الهيكل القديم إلى هيكل Clean Architecture الجديد.

خريطة التحويل:
    data.land_database          → core.domain.land_database
    search_engine               → core.matchmaking.service
    ai.glm_client              → core.ai.llm.glm_client
    ai.ollama_service          → core.ai.llm.ollama_service
    ai.llm_router              → core.ai.llm.router
    ai.tft_model               → core.ai.tft.model
    ai.tft_training            → core.ai.tft.training
    ai.tft_airflow_dag         → core.ai.tft.airflow_dag
    geological.service         → core.geological.service
    geological.soil_service    → core.geological.soil_service
    geological.groundwater_service → core.geological.groundwater_service
    geological.egsma_reader    → infrastructure.external.geological.egsma_reader
    geological.gee_client      → infrastructure.external.geological.gee_client
    payment.base               → core.financial.base
    payment.fawry_gateway      → infrastructure.external.payment.fawry_gateway
    payment.stripe_gateway     → infrastructure.external.payment.stripe_gateway
    payment.transaction_service → core.financial.service
    customer_service.hub       → core.customer_service.hub
    customer_service.rag_chatbot → core.customer_service.rag_chatbot
    customer_service.survey_service → core.customer_service.survey_service
    customer_service.whatsapp_service → infrastructure.external.whatsapp_service
    customer_service.zendesk_client   → infrastructure.external.zendesk_client
    shared (in microservices)    → core.domain.entities

الاستخدام:
    python refactor_imports.py              # إظهار التغييرات فقط (dry-run)
    python refactor_imports.py --apply      # تطبيق التغييرات فعلاً
    python refactor_imports.py --apply --delete-old  # تطبيق + حذف الملفات القديمة

الخيارات:
    --apply          تطبيق التعديلات فعلياً (بدونها يعرض فقط)
    --delete-old     حذف الملفات/المجلدات القديمة بعد النقل
    --verbose        عرض تفاصيل أكثر
    --diff           عرض الفروقات (diff)
"""

import os
import re
import sys
import ast
import difflib
import argparse
import textwrap
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set

# ══════════════════════════════════════════════
# إعدادات
# ══════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parent

# المجلدات القديمة المراد حذفها (بعد النقل الناجح)
OLD_DIRS_TO_DELETE = [
    "data",
    "models",
]

# المجلدات المحذوفة بالفعل (لا تُفحَّص — موجودة فقط كمرجع تاريخي)
ALREADY_DELETED_DIRS = [
    "ai",                  # ← حُذف: النسخة الأصلية في الجذر
    "customer_service",    # ← حُذف: core.customer_service هو المصدر
    "geological",          # ← حُذف: core.geological + infrastructure.external.geological
]

# الملفات القديمة المراد حذفها (في الجذر)
OLD_FILES_TO_DELETE = [
    "search_engine.py",
    "app.py",
    "Dockerfile.streamlit",
]

# ══════════════════════════════════════════════
# خريطة تحويل المسارات (old_module → new_module)
# ══════════════════════════════════════════════

IMPORT_MAP: Dict[str, str] = {
    # ── data/ → core/domain/ ──
    "data.land_database":          "core.domain.land_database",
    "data":                        "core.domain",

    # ── search_engine.py → core/matchmaking/ ──
    "search_engine":               "core.matchmaking.service",

    # ── ai/ → core/ai/ ──
    "ai.glm_client":               "core.ai.llm.glm_client",
    "ai.ollama_service":           "core.ai.llm.ollama_service",
    "ai.llm_router":               "core.ai.llm.router",
    "ai.tft_model":                "core.ai.tft.model",
    "ai.tft_training":             "core.ai.tft.training",
    "ai.tft_airflow_dag":          "core.ai.tft.airflow_dag",

    # ── geological/ → core/geological/ + infrastructure/ ──
    "geological.service":          "core.geological.service",
    "geological.soil_service":     "core.geological.soil_service",
    "geological.groundwater_service": "core.geological.groundwater_service",
    "geological.egsma_reader":     "infrastructure.external.geological.egsma_reader",
    "geological.gee_client":       "infrastructure.external.geological.gee_client",

    # ── payment/ → core/financial/ + infrastructure/ ──
    "payment.base":                "core.financial.base",
    "payment.fawry_gateway":       "infrastructure.external.payment.fawry_gateway",
    "payment.stripe_gateway":      "infrastructure.external.payment.stripe_gateway",
    "payment.transaction_service": "core.financial.service",
    "payment.wallet_store":         "core.financial.service",
    "payment.transaction_store":     "core.financial.service",
    "payment.idempotency_provider": "core.financial.service",
    "payment.payment_processor":    "core.financial.service",
    "payment.webhook_handler":     "core.financial.service",
    "payment.refund_manager":       "core.financial.service",
    "payment.models":               "payment.models",  # يبقى في مكانه (ORM نماذج فريدة)

    # ── customer_service/ → core/customer_service/ + infrastructure/ ──
    "customer_service.hub":        "core.customer_service.hub",
    "customer_service.rag_chatbot": "core.customer_service.rag_chatbot",
    "customer_service.survey_service": "core.customer_service.survey_service",
    "customer_service.whatsapp_service": "infrastructure.external.whatsapp_service",
    "customer_service.zendesk_client":   "infrastructure.external.zendesk_client",

    # ── microservices/shared → core/domain/entities ──
    "shared":                      "core.domain.entities",
    "shared.models":                "core.domain.entities",

    # ── استيرادات نسبية (غير prefixed) كانت تعمل عبر sys.path ──
    "account_store":               "core.account.store",
    "geological.service":          "core.geological.service",
}

# خريطة تحويل خاصة بـ sys.path.insert (لأن بعض الملفات تستخدم sys.path)
# في الهيكل الجديد، sys.path يجب أن يشير إلى PROJECT_ROOT فقط
# وليس إلى مجلدات فرعية

# الملفات التي يجب تخطيها (لا تُعدّل — لأنها ملفات إعداد أو لا تحتوي استيرادات داخلية)
SKIP_DIRS = {
    "microservices",       # نحتفظ بالميكروسيرفيس كمرجع (Docker/K8s)
    "__pycache__",
    ".git",
    "node_modules",
    ".eggs",
    "dist",
    "build",
    "*.egg-info",
}


# ══════════════════════════════════════════════
# محرك التحويل
# ══════════════════════════════════════════════

class ImportRefactorer:
    """
    محرر مسارات الاستيراد.

    يقرأ ملف .py ويُحدّث جميع عبارات:
        - from X import Y   →   from NEW_X import Y
        - import X          →   import NEW_X
    """

    def __init__(self, import_map: Dict[str, str], verbose: bool = False):
        self.import_map = import_map
        # ترتيب حسب الطول (الأطول أولاً) لمنع التحويل الجزئي
        # مثلاً: "data.land_database" يجب أن يسبق "data"
        self.sorted_keys = sorted(import_map.keys(), key=len, reverse=True)
        self.verbose = verbose
        self.stats = {
            "files_scanned": 0,
            "files_modified": 0,
            "imports_changed": 0,
            "errors": [],
        }

    def _find_new_module(self, old_module: str) -> Optional[str]:
        """إيجاد الوحدة الجديدة المطابقة."""
        for old_key in self.sorted_keys:
            if old_module == old_key or old_module.startswith(old_key + "."):
                # حساب الباقي (sub-modules)
                remainder = old_module[len(old_key):]
                if remainder.startswith("."):
                    remainder = remainder[1:]
                new_base = self.import_map[old_key]
                if remainder:
                    return f"{new_base}.{remainder}"
                return new_base
        return None

    def refactor_content(self, content: str, filepath: str) -> Tuple[str, int]:
        """
        تحديث جميع الاستيرادات في محتوى ملف واحد.

        Args:
            content: نص الملف
            filepath: مسار الملف (للتسجيل)

        Returns:
            (new_content, changes_count)
        """
        changes = 0
        lines = content.split("\n")
        new_lines = []

        for line in lines:
            new_line = self._refactor_line(line)
            if new_line != line:
                changes += 1
            new_lines.append(new_line)

        return "\n".join(new_lines), changes

    def _refactor_line(self, line: str) -> str:
        """تحويل سطر واحد."""
        # نمط 1: from X import Y, Z, ...
        m_from = re.match(r'^(\s*from\s+)([\w.]+)(\s+import\s+.*)$', line)
        if m_from:
            prefix, old_mod, suffix = m_from.groups()
            new_mod = self._find_new_module(old_mod)
            if new_mod and new_mod != old_mod:
                if self.verbose:
                    print(f"    from {old_mod} → from {new_mod}")
                return f"{prefix}{new_mod}{suffix}"
            return line

        # نمط 1.5: from X import Y where X has no dots (bare module like account_store)
        if not m_from:
            m_from = re.match(r'^(\s*from\s+)([\w]+)(\s+import\s+.*)$', line)

        # نمط 2: import X [as Y]
        m_import = re.match(r'^(\s*import\s+)([\w.]+)(\s*(?:as\s+\w+)?)\s*$', line)
        if m_import:
            prefix, old_mod, suffix = m_import.groups()
            new_mod = self._find_new_module(old_mod)
            if new_mod and new_mod != old_mod:
                if self.verbose:
                    print(f"    import {old_mod} → import {new_mod}")
                return f"{prefix}{new_mod}{suffix}"
            return line

        # نمط 3: استيراد داخل تعبير (نادر لكن يحدث)
        # from X import (Y\n, Z)
        m_from_multi = re.match(r'^(\s*from\s+)([\w.]+)(\s+import\s*\(.*)$', line)
        if m_from_multi:
            prefix, old_mod, suffix = m_from_multi.groups()
            new_mod = self._find_new_module(old_mod)
            if new_mod and new_mod != old_mod:
                if self.verbose:
                    print(f"    from {old_mod} → from {new_mod}")
                return f"{prefix}{new_mod}{suffix}"
            return line

        return line

    def refactor_file(self, filepath: Path, apply: bool = False) -> Tuple[bool, int, str]:
        """
        معالجة ملف واحد.

        Returns:
            (was_modified, changes_count, diff_text)
        """
        try:
            content = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError) as e:
            self.stats["errors"].append(f"Cannot read {filepath}: {e}")
            return False, 0, ""

        new_content, changes = self.refactor_content(str(content), str(filepath))

        if changes == 0:
            return False, 0, ""

        # تحقق من صحة النتيجة بـ AST
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            self.stats["errors"].append(
                f"Syntax error after refactoring {filepath}: line {e.lineno}: {e.msg}"
            )
            return False, 0, ""

        # عرض الفروقات
        diff = ""
        old_lines = content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=str(filepath),
            tofile=str(filepath),
            n=1,
        ))

        if apply:
            filepath.write_text(new_content, encoding="utf-8")
            self.stats["imports_changed"] += changes

        self.stats["files_modified"] += 1
        return True, changes, diff

    def scan_directory(
        self,
        root: Path,
        apply: bool = False,
        show_diff: bool = False,
    ) -> None:
        """مسح جميع ملفات .py وتحويلها."""
        py_files = sorted(root.rglob("*.py"))

        # فلترة المجلدات المتخطاة
        skip_parts = {s.strip("*") for s in SKIP_DIRS}
        filtered = []
        for fp in py_files:
            rel = fp.relative_to(root)
            if any(part in skip_parts for part in rel.parts):
                continue
            filtered.append(fp)

        self.stats["files_scanned"] = len(filtered)

        for filepath in filtered:
            modified, changes, diff = self.refactor_file(filepath, apply=apply)

            if modified:
                rel = filepath.relative_to(root)
                if apply:
                    print(f"  ✏️  {rel} ({changes} تعديلات)")
                else:
                    print(f"  🔍 {rel} ({changes} تعديلات مقترحة)")

                if show_diff and diff:
                    # عرض diff ملون (اختصار)
                    for line in diff.split("\n"):
                        if line.startswith("-") and not line.startswith("---"):
                            print(f"      \033[91m{line}\033[0m")
                        elif line.startswith("+") and not line.startswith("+++"):
                            print(f"      \033[92m{line}\033[0m")
                        else:
                            print(f"      {line}")

    def remove_old_files(self, root: Path, apply: bool = False) -> List[str]:
        """
        حذف الملفات والمجلدات القديمة.

        Returns:
            قائمة بالمسارات المحذوفة (أو المقترحة للحذف)
        """
        removed = []

        # حذف الملفات القديمة
        for filename in OLD_FILES_TO_DELETE:
            fpath = root / filename
            if fpath.exists():
                if apply:
                    fpath.unlink()
                    print(f"  🗑️  حذف ملف: {filename}")
                else:
                    print(f"  🗑️  سيُحذف: {filename}")
                removed.append(str(fpath))

        # حذف المجلدات القديمة
        for dirname in OLD_DIRS_TO_DELETE:
            dpath = root / dirname
            if dpath.is_dir():
                # تحقق أن المجلد فارغ (بعد نقل الملفات)
                py_count = len(list(dpath.rglob("*.py")))
                if py_count > 0 and not apply:
                    print(f"  ⚠️  {dirname}/ يحتوي {py_count} ملف .py — تأكد من النقل أولاً")
                if apply and py_count == 0:
                    import shutil
                    shutil.rmtree(dpath)
                    print(f"  🗑️  حذف مجلد: {dirname}/")
                elif apply and py_count > 0:
                    print(f"  ⚠️  تخطي {dirname}/ — يحتوي {py_count} ملف (غير فارغ)")
                else:
                    print(f"  🗑️  سيُحذف: {dirname}/")
                removed.append(str(dpath))

        return removed


# ══════════════════════════════════════════════
# التحقق بعد التحويل
# ══════════════════════════════════════════════

def validate_all_files(root: Path) -> Tuple[int, int, List[str]]:
    """
    التحقق من صحة جميع ملفات .py بـ ast.parse.

    Returns:
        (valid_count, invalid_count, errors)
    """
    valid = 0
    invalid = 0
    errors = []

    skip_parts = {s.strip("*") for s in SKIP_DIRS}
    for fp in sorted(root.rglob("*.py")):
        rel = fp.relative_to(root)
        if any(part in skip_parts for part in rel.parts):
            continue

        try:
            content = fp.read_text(encoding="utf-8")
            ast.parse(content)
            valid += 1
        except SyntaxError as e:
            invalid += 1
            errors.append(f"  ✗ {rel}: line {e.lineno}: {e.msg}")
        except Exception as e:
            invalid += 1
            errors.append(f"  ✗ {rel}: {type(e).__name__}: {e}")

    return valid, invalid, errors


def print_import_map() -> None:
    """عرض خريطة التحويل الكاملة."""
    print("\n" + "=" * 70)
    print("خريطة تحويل المسارات (Import Refactoring Map)")
    print("=" * 70)

    # تجميع حسب الطبقة
    layers = {
        "core/domain": [],
        "core/matchmaking": [],
        "core/ai": [],
        "core/geological": [],
        "core/financial": [],
        "core/customer_service": [],
        "core/account": [],
        "infrastructure/external": [],
        "infrastructure/monitoring": [],
    }

    for old, new in IMPORT_MAP.items():
        matched = False
        for layer_key in layers:
            if new.startswith(layer_key):
                layers[layer_key].append((old, new))
                matched = True
                break
        if not matched:
            layers.setdefault("أخرى", []).append((old, new))

    for layer, mappings in layers.items():
        if not mappings:
            continue
        print(f"\n  📁 {layer}/")
        for old, new in mappings:
            print(f"     {old:<45s} → {new}")

    print()


def print_new_structure() -> None:
    """عرض هيكل المشروع الجديد."""
    print("\n" + "=" * 70)
    print("هيكل Clean Architecture الجديد")
    print("=" * 70)

    structure = """
smart-land-copilot-v4-arabic/
├── config/                          ← إعدادات التطبيق (Settings, .env)
│   ├── __init__.py
│   └── settings.py                  ← Settings dataclass — جميع المتغيرات
│
├── core/                            ← منطق الأعمال (Business Logic)
│   ├── domain/                      ← الكيانات والأنواع المشتركة
│   │   ├── __init__.py
│   │   ├── entities/                ← Pydantic models (UserRole, LandBrief, ...)
│   │   │   ├── __init__.py
│   │   │   └── shared_models.py
│   │   ├── enums/                   ← أنواع التعداد
│   │   └── ports/                   ← Abstract interfaces (Dependency Inversion)
│   │
│   ├── matchmaking/                 ← محرك المطابقة الاستباقي
│   │   ├── __init__.py
│   │   └── service.py               ← InvestorCriteria, MatchResult, ...
│   │
│   ├── ai/                          ← الذكاء الاصطناعي
│   │   ├── llm/                     ← نماذج اللغة
│   │   │   ├── glm_client.py        ← GLM-5 Turbo (OpenRouter)
│   │   │   ├── ollama_service.py    ← Ollama Local Fallback
│   │   │   └── router.py            ← LLM Router (3-level Fallback)
│   │   └── tft/                     ← Temporal Fusion Transformer
│   │       ├── model.py             ← create_tft_model()
│   │       ├── training.py          ← train_tft_model()
│   │       └── airflow_dag.py       ← retrain_model_airflow()
│   │
│   ├── geological/                  ← البيانات الجيولوجية (النواة)
│   │   ├── service.py               ← GeologicalService (منسق)
│   │   ├── soil_service.py          ← بيانات التربة
│   │   └── groundwater_service.py   ← بيانات المياه الجوفية
│   │
│   ├── financial/                   ← الخدمة المالية
│   │   ├── base.py                  ← PaymentGateway (Abstract), Types
│   │   └── service.py               ← TransactionService, WalletStore
│   │
│   ├── customer_service/            ← خدمة العملاء (النواة)
│   │   ├── hub.py                   ← CustomerServiceHub
│   │   ├── rag_chatbot.py           ← RAG Chatbot
│   │   └── survey_service.py        ← استبيانات الرضا
│   │
│   ├── prediction/                  ← خدمة التنبؤ بالأسعار
│   │   └── service.py               ← TFT prediction endpoints
│   │
│   └── account/                     ← خدمة الحسابات
│       └── store.py                 ← InvestorStore, LandownerStore
│
├── infrastructure/                  ← التكاملات الخارجية (External)
│   ├── external/
│   │   ├── geological/              ← GEE, EGSMA (API clients)
│   │   │   ├── gee_client.py
│   │   │   └── egsma_reader.py
│   │   └── payment/                 ← بوابات الدفع
│   │       ├── fawry_gateway.py
│   │       └── stripe_gateway.py
│   │
│   ├── persistence/                 ← التخزين
│   │   └── account_store.py         ← In-memory account data
│   │
│   ├── monitoring/                  ← المراقبة (Prometheus, Sentry)
│   │   ├── metrics_middleware.py
│   │   └── sentry_init.py
│   │
│   └── orchestration/               ← Docker Compose, Airflow configs
│
├── api/                             ← طبقة HTTP/API (FastAPI Routes)
│   ├── routes/
│   │   ├── auth.py                  ← /api/auth/*
│   │   ├── land.py                  ← /api/lands/*
│   │   └── account.py               ← /api/v1/investors/*, /api/v1/landowners/*
│   └── middleware/
│       └── __init__.py              ← Metrics, Sentry middleware
│
├── web/                             ← واجهة المستخدم (Streamlit)
│   ├── app.py                       ← التطبيق الرئيسي
│   └── Dockerfile
│
├── tests/                           ← الاختبارات
│
├── microservices/                   ← Docker/K8s configs (مرجع)
│   ├── docker-compose.yml
│   ├── k8s/
│   └── ...
│
├── refactor_imports.py              ← هذا السكربت
├── requirements.txt
└── worklog.md
"""
    print(structure)


# ══════════════════════════════════════════════
# الدالة الرئيسية
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="سكربت إعادة هيكلة مسارات الاستيراد — Clean Architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            أمثلة:
              python refactor_imports.py              # عرض التغييرات فقط (dry-run)
              python refactor_imports.py --apply      # تطبيق التغييرات
              python refactor_imports.py --apply --delete-old  # تطبيق + حذف القديم
              python refactor_imports.py --map        # عرض خريطة التحويل
              python refactor_imports.py --structure  # عرض الهيكل الجديد
        """),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="تطبيق التعديلات فعلياً (بدونها = dry-run فقط)",
    )
    parser.add_argument(
        "--delete-old",
        action="store_true",
        help="حذف الملفات والمجلدات القديمة (يتطلب --apply)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="عرض تفاصيل أكثر عن كل تعديل",
    )
    parser.add_argument(
        "--diff", "-d",
        action="store_true",
        help="عرض الفروقات (diff) لكل ملف",
    )
    parser.add_argument(
        "--map",
        action="store_true",
        help="عرض خريطة تحويل المسارات فقط",
    )
    parser.add_argument(
        "--structure",
        action="store_true",
        help="عرض هيكل Clean Architecture الجديد فقط",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="التحقق من صحة جميع الملفات بـ ast.parse",
    )

    args = parser.parse_args()

    # ── عرض المعلومات فقط ──
    if args.map:
        print_import_map()
        return 0

    if args.structure:
        print_new_structure()
        return 0

    if args.validate:
        print("\n🔍 التحقق من صحة الملفات (ast.parse)...")
        valid, invalid, errors = validate_all_files(PROJECT_ROOT)
        print(f"\n  ✅ صالحة: {valid} ملف")
        if invalid > 0:
            print(f"  ❌ أخطاء: {invalid} ملف")
            for err in errors:
                print(err)
        else:
            print("  🎉 جميع الملفات صالحة!")
        return 0 if invalid == 0 else 1

    # ── التحويل ──
    mode = "تطبيق فعلي ✏️" if args.apply else "dry-run 🔍"
    print(f"\n{'=' * 70}")
    print(f"إعادة هيكلة الاستيرادات — Clean Architecture ({mode})")
    print(f"{'=' * 70}")
    print(f"  المشروع: {PROJECT_ROOT}")
    print(f"  عدد التحويلات في الخريطة: {len(IMPORT_MAP)}")
    print()

    refactored = ImportRefactorer(IMPORT_MAP, verbose=args.verbose)

    # تحويل الملفات في الطبقات الجديدة
    new_layers = ["config", "core", "infrastructure", "api", "web"]
    for layer in new_layers:
        layer_path = PROJECT_ROOT / layer
        if not layer_path.is_dir():
            continue

        print(f"  📁 {layer}/")
        refactored.scan_directory(
            layer_path,
            apply=args.apply,
            show_diff=args.diff,
        )

    # تحويل الملفات في الجذر
    print(f"  📁 (الجذر)")
    root_py = [f for f in PROJECT_ROOT.glob("*.py") if f.name != "refactor_imports.py"]
    for fp in root_py:
        modified, changes, diff = refactored.refactor_file(fp, apply=args.apply)
        if modified:
            if args.apply:
                print(f"  ✏️  {fp.name} ({changes} تعديلات)")
            else:
                print(f"  🔍 {fp.name} ({changes} تعديلات مقترحة)")

    # ── الإحصائيات ──
    print(f"\n{'─' * 70}")
    print(f"  الإحصائيات:")
    print(f"    ملفات ممسوحة:   {refactored.stats['files_scanned']}")
    print(f"    ملفات معدّلة:   {refactored.stats['files_modified']}")
    print(f"    استيرادات غُيّرت: {refactored.stats['imports_changed']}")

    if refactored.stats["errors"]:
        print(f"\n  ⚠️  أخطاء ({len(refactored.stats['errors'])}):")
        for err in refactored.stats["errors"]:
            print(f"    {err}")

    # ── حذف الملفات القديمة ──
    if args.delete_old:
        if not args.apply:
            print("\n  ⚠️  --delete-old يتطلب --apply")
            return 1

        print(f"\n{'─' * 70}")
        print("  🗑️  حذف الملفات القديمة:")
        refactored.remove_old_files(PROJECT_ROOT, apply=True)

    # ── التحقق النهائي ──
    if args.apply:
        print(f"\n{'─' * 70}")
        print("  🔍 التحقق النهائي (ast.parse)...")
        valid, invalid, errors = validate_all_files(PROJECT_ROOT)
        print(f"    ✅ صالحة: {valid} ملف")
        if invalid > 0:
            print(f"    ❌ أخطاء: {invalid} ملف")
            for err in errors:
                print(err)
            return 1
        else:
            print("    🎉 جميع الملفات صالحة بعد إعادة الهيكلة!")

    print(f"\n{'=' * 70}")
    if not args.apply:
        print("  💡 أضف --apply لتطبيق التغييرات فعلياً")
        print("  💡 أضف --apply --delete-old لحذف الملفات القديمة")
    else:
        print("  ✅ تم إعادة الهيكلة بنجاح!")
    print(f"{'=' * 70}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())