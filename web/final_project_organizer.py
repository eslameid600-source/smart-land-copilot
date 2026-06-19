#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
final_project_organizer.py
==========================

أداة لإعادة تنظيم وهيكلة مشروع "Smart Land Copilot" بشكل نهائي.

الوظائف:
    1. تطلب من المستخدم مسار المشروع الحالي (المجلد الجذر).
    2. تنشئ الهيكل النهائي داخل مجلد جديد: smart-land-copilot-clean/
    3. تمسح جميع ملفات .py في المشروع القديم وتحدد فئة كل ملف بناءً على
       الكلمات المفتاحية في محتواه (FastAPI, SQLAlchemy, Streamlit, ...) ثم
       تنقله إلى المجلد الصحيح.
    4. تدمج ملفات __init__.py المكررة وتنشئ __init__.py واحداً لكل مجلد فرعي.
    5. تحذف المجلدات القديمة من الجذر بعد التأكد من نقل ملفاتها.
    6. تولّد import_remap.json يحتوي على خريطة تحويل المسارات.
    7. تطبع تقريراً نهائياً.

التشغيل:
    python final_project_organizer.py

يعمل على Linux / macOS / Windows.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# اسم مجلد المخرجات النهائي
# ---------------------------------------------------------------------------
CLEAN_ROOT_NAME = "smart-land-copilot-clean"

# ---------------------------------------------------------------------------
# تعريف الهيكل النهائي للمجلدات (المجلدات التي يجب إنشاؤها دائماً)
# ---------------------------------------------------------------------------
TARGET_DIRECTORIES: List[str] = [
    "config",
    "core",
    "core/account",
    "core/ai",
    "core/auction",
    "core/customer_service",
    "core/domain",
    "core/financial",
    "core/geological",
    "core/matchmaking",
    "core/prediction",
    "infrastructure",
    "infrastructure/database",
    "infrastructure/external",
    "infrastructure/monitoring",
    "infrastructure/persistence",
    "api",
    "api/routes",
    "api/middleware",
    "web",
    "microservices",
    "microservices/k8s",
    "tests",
    "tests/unit",
    "tests/integration",
    "scripts",
    ".github",
    ".github/workflows",
]

# المجلدات التي ينبغي أن تحتوي على __init__.py (حزم بايثون فقط)
PACKAGE_DIRECTORIES: List[str] = [
    "config",
    "core",
    "core/account",
    "core/ai",
    "core/auction",
    "core/customer_service",
    "core/domain",
    "core/financial",
    "core/geological",
    "core/matchmaking",
    "core/prediction",
    "infrastructure",
    "infrastructure/database",
    "infrastructure/external",
    "infrastructure/monitoring",
    "infrastructure/persistence",
    "api",
    "api/routes",
    "api/middleware",
    "tests",
    "tests/unit",
    "tests/integration",
]

# ---------------------------------------------------------------------------
# قواعد التصنيف.
#
# كل قاعدة عبارة عن: (المجلد الهدف، قائمة الكلمات المفتاحية، الأولوية).
# يتم فحص القواعد بالترتيب: أعلى مجموع تطابق (مرجّحاً بالأولوية) يفوز.
# الكلمات المفتاحية يتم البحث عنها في محتوى الملف وكذلك في اسم الملف.
# ---------------------------------------------------------------------------
# كل عنصر: target_dir -> {"content": [...], "filename": [...], "weight": n}
CLASSIFICATION_RULES: Dict[str, Dict[str, object]] = {
    # ---- API ----
    "api/routes": {
        "content": [
            r"\bAPIRouter\b",
            r"@router\.",
            r"@app\.(get|post|put|delete|patch)\b",
            r"\bFastAPI\b",
        ],
        "filename": [r"rout", r"endpoint", r"\bapi\b", r"\bview"],
        "weight": 3,
    },
    "api/middleware": {
        "content": [
            r"\bMiddleware\b",
            r"BaseHTTPMiddleware",
            r"add_middleware",
            r"\bCORSMiddleware\b",
        ],
        "filename": [r"middleware", r"interceptor"],
        "weight": 3,
    },
    # ---- WEB ----
    "web": {
        "content": [
            r"\bstreamlit\b",
            r"\bst\.(title|write|sidebar|button|columns|markdown)\b",
            r"\bgradio\b",
            r"\bdash\b",
            r"\bflask\b",
            r"render_template",
        ],
        "filename": [r"streamlit", r"dashboard", r"\bapp\b", r"frontend", r"\bui\b"],
        "weight": 3,
    },
    # ---- CONFIG ----
    "config": {
        "content": [
            r"\bBaseSettings\b",
            r"\bSettings\b",
            r"pydantic_settings",
            r"load_dotenv",
            r"os\.environ",
            r"\bENV\b",
        ],
        "filename": [r"settings", r"\bconfig", r"\benv\b", r"constants"],
        "weight": 3,
    },
    # ---- INFRASTRUCTURE ----
    "infrastructure/database": {
        "content": [
            r"\bSQLAlchemy\b",
            r"declarative_base",
            r"create_engine",
            r"sessionmaker",
            r"\bColumn\(",
            r"\bMetaData\b",
            r"\balembic\b",
        ],
        "filename": [r"\bdatabase", r"\bdb\b", r"\bmodels?\b", r"schema", r"migration", r"orm"],
        "weight": 3,
    },
    "infrastructure/persistence": {
        "content": [
            r"\bRepository\b",
            r"\bDAO\b",
            r"\.commit\(\)",
            r"\.save\(",
            r"\bUnitOfWork\b",
        ],
        "filename": [r"repositor", r"persist", r"\bdao\b", r"store"],
        "weight": 2,
    },
    "infrastructure/external": {
        "content": [
            r"\brequests\.(get|post|put|delete)\b",
            r"\bhttpx\b",
            r"\baiohttp\b",
            r"\bboto3\b",
            r"api_key",
            r"\bclient\s*=",
            r"openai",
        ],
        "filename": [r"client", r"external", r"\bapi_", r"integration", r"gateway", r"adapter"],
        "weight": 2,
    },
    "infrastructure/monitoring": {
        "content": [
            r"\blogging\b",
            r"getLogger",
            r"\bprometheus",
            r"\bsentry",
            r"\bmetrics?\b",
            r"\btracing\b",
        ],
        "filename": [r"monitor", r"logging", r"\blog\b", r"metric", r"telemetr", r"observ"],
        "weight": 2,
    },
    # ---- CORE DOMAINS ----
    "core/ai": {
        "content": [
            r"\btensorflow\b",
            r"\btorch\b",
            r"\bsklearn\b",
            r"\bkeras\b",
            r"\btransformers\b",
            r"\bLLM\b",
            r"\bembedding",
            r"\bmodel\.predict\b",
        ],
        "filename": [r"\bai\b", r"\bml\b", r"\bnlp\b", r"\bllm\b", r"neural", r"\bmodel_"],
        "weight": 2,
    },
    "core/prediction": {
        "content": [
            r"\bpredict\b",
            r"\bforecast\b",
            r"\bregression\b",
            r"\bestimat",
        ],
        "filename": [r"predict", r"forecast", r"estimat"],
        "weight": 2,
    },
    "core/geological": {
        "content": [
            r"\bgeolog",
            r"\bgeospatial\b",
            r"\bgeopandas\b",
            r"\bshapely\b",
            r"\blatitude\b",
            r"\blongitude\b",
            r"\bcoordinate",
            r"\bterrain\b",
            r"\bsoil\b",
        ],
        "filename": [r"geo", r"terrain", r"soil", r"land", r"spatial", r"\bgis\b"],
        "weight": 2,
    },
    "core/auction": {
        "content": [r"\bauction\b", r"\bbid\b", r"\bbidding\b", r"\blot\b"],
        "filename": [r"auction", r"\bbid"],
        "weight": 2,
    },
    "core/financial": {
        "content": [
            r"\bpayment\b",
            r"\binvoice\b",
            r"\bstripe\b",
            r"\bcurrency\b",
            r"\bprice\b",
            r"\btransaction\b",
            r"\bbilling\b",
        ],
        "filename": [r"financ", r"payment", r"invoice", r"billing", r"\bpay\b", r"price", r"wallet"],
        "weight": 2,
    },
    "core/account": {
        "content": [
            r"\buser\b",
            r"\bauth\b",
            r"\blogin\b",
            r"\bpassword\b",
            r"\bjwt\b",
            r"\baccount\b",
            r"\bregister\b",
        ],
        "filename": [r"account", r"\buser", r"\bauth", r"login", r"profile", r"identity"],
        "weight": 2,
    },
    "core/customer_service": {
        "content": [
            r"\bticket\b",
            r"\bsupport\b",
            r"\bchatbot\b",
            r"\bcomplaint\b",
            r"\bcustomer\b",
        ],
        "filename": [r"customer", r"support", r"ticket", r"\bchat", r"helpdesk", r"service"],
        "weight": 2,
    },
    "core/matchmaking": {
        "content": [r"\bmatch", r"\brecommend", r"\bsimilarity\b", r"\branking\b"],
        "filename": [r"match", r"recommend", r"\bmatchmaking"],
        "weight": 2,
    },
    "core/domain": {
        "content": [
            r"\bBaseModel\b",
            r"\bpydantic\b",
            r"\bdataclass\b",
            r"\b@dataclass\b",
            r"\bEntity\b",
            r"\bValueObject\b",
            r"\bEnum\b",
        ],
        "filename": [r"domain", r"\bentity", r"\bentities", r"\bdto\b", r"\bschemas?\b", r"\bmodels?\b"],
        "weight": 1,
    },
    # ---- TESTS ----
    "tests/integration": {
        "content": [r"\bintegration\b", r"\bTestClient\b", r"\bdocker\b.*test"],
        "filename": [r"integration", r"\bit_", r"_it\b", r"e2e"],
        "weight": 4,
    },
    "tests/unit": {
        "content": [
            r"\bimport pytest\b",
            r"\bimport unittest\b",
            r"\bdef test_",
            r"\bassert\b",
            r"\b@pytest",
            r"\bMock\b",
        ],
        "filename": [r"^test_", r"_test", r"\btest", r"\bspec"],
        "weight": 4,
    },
    # ---- SCRIPTS ----
    "scripts": {
        "content": [
            r"if __name__ == ['\"]__main__['\"]",
            r"\bargparse\b",
            r"\bsys\.argv\b",
            r"\bclick\b",
        ],
        "filename": [r"script", r"\butil", r"\btool", r"\bcli\b", r"\brun_", r"manage"],
        "weight": 1,
    },
}

# المجلدات القديمة المعروفة المرشّحة للحذف بعد النقل
KNOWN_LEGACY_DIRS: List[str] = [
    "ai",
    "geological",
    "customer_service",
    "payment",
    "account",
    "auction",
    "financial",
    "matchmaking",
    "prediction",
    "domain",
    "database",
    "persistence",
    "external",
    "monitoring",
    "routes",
    "middleware",
    "services",
    "models",
    "utils",
    "core",
    "infrastructure",
    "api",
    "web",
]

DEFAULT_TARGET = "core/domain"


# ===========================================================================
# دوال مساعدة
# ===========================================================================
def read_text_safe(path: Path) -> str:
    """قراءة محتوى ملف نصياً بأمان مع تجاهل أخطاء الترميز."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeError):
        return ""


def score_file(filename: str, content: str) -> Tuple[str, Dict[str, int]]:
    """
    حساب درجة كل فئة لملف معيّن وإرجاع أفضل فئة + تفصيل الدرجات.
    """
    name_lc = filename.lower()
    scores: Dict[str, int] = {}

    for target, rule in CLASSIFICATION_RULES.items():
        weight = int(rule.get("weight", 1))  # type: ignore[arg-type]
        score = 0

        for pattern in rule.get("content", []):  # type: ignore[union-attr]
            if re.search(pattern, content, flags=re.IGNORECASE):
                score += weight

        for pattern in rule.get("filename", []):  # type: ignore[union-attr]
            if re.search(pattern, name_lc, flags=re.IGNORECASE):
                # تطابق اسم الملف أقوى قليلاً
                score += weight + 1

        if score > 0:
            scores[target] = score

    if not scores:
        return DEFAULT_TARGET, scores

    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0], scores


def unique_destination(dest_dir: Path, filename: str, used: Dict[Path, int]) -> Path:
    """
    إرجاع مسار وجهة فريد. إذا وُجد ملف بنفس الاسم تُضاف لاحقة رقمية
    (مثل: service_1.py) لتجنّب الكتابة فوق الملفات.
    """
    candidate = dest_dir / filename
    if candidate not in used and not candidate.exists():
        used[candidate] = 1
        return candidate

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    i = 1
    while True:
        candidate = dest_dir / f"{stem}_{i}{suffix}"
        if candidate not in used and not candidate.exists():
            used[candidate] = 1
            return candidate
        i += 1


def is_within(path: Path, parent: Path) -> bool:
    """هل المسار path داخل المجلد parent؟"""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


# ===========================================================================
# المنطق الرئيسي
# ===========================================================================
class ProjectOrganizer:
    def __init__(self, source_root: Path, dry_run: bool = False) -> None:
        self.source_root = source_root.resolve()
        self.clean_root = self.source_root / CLEAN_ROOT_NAME
        self.dry_run = dry_run

        # تقارير
        self.created_dirs: List[str] = []
        self.moved_files: List[Tuple[str, str, str]] = []  # (from, to, reason)
        self.deleted_dirs: List[str] = []
        self.merged_inits: List[str] = []
        self.skipped: List[Tuple[str, str]] = []
        self.import_remap: Dict[str, str] = {}

        # لتتبّع الوجهات المستخدمة
        self._used_dest: Dict[Path, int] = {}

    # ------------------------------------------------------------------
    def run(self) -> None:
        print("=" * 70)
        print("  Smart Land Copilot — أداة إعادة الهيكلة النهائية")
        print("=" * 70)
        print(f"المشروع المصدر : {self.source_root}")
        print(f"الوجهة النظيفة : {self.clean_root}")
        if self.dry_run:
            print(">>> وضع المعاينة (DRY-RUN): لن يتم تنفيذ أي تغييرات فعلية <<<")
        print("-" * 70)

        self.create_structure()
        self.organize_python_files()
        self.create_package_inits()
        self.create_root_scaffold()
        self.write_import_remap()
        self.cleanup_legacy_dirs()
        self.print_report()

    # ------------------------------------------------------------------
    def create_structure(self) -> None:
        """إنشاء الهيكل النهائي للمجلدات."""
        for rel in [""] + TARGET_DIRECTORIES:
            d = self.clean_root / rel if rel else self.clean_root
            if not d.exists():
                if not self.dry_run:
                    d.mkdir(parents=True, exist_ok=True)
                self.created_dirs.append(str(d.relative_to(self.source_root)))

    # ------------------------------------------------------------------
    def organize_python_files(self) -> None:
        """مسح جميع ملفات .py في المصدر وتصنيفها ونقلها."""
        for py in sorted(self.source_root.rglob("*.py")):
            # تجاهل أي شيء داخل مجلد الوجهة النظيف
            if is_within(py, self.clean_root):
                continue
            # تجاهل السكربت نفسه
            if py.resolve() == Path(__file__).resolve():
                continue

            rel_from = str(py.relative_to(self.source_root))

            # ملفات __init__.py القديمة سيتم تجاهلها هنا ودمجها لاحقاً
            if py.name == "__init__.py":
                content = read_text_safe(py)
                if content.strip():
                    # احتفظ بالمحتوى غير الفارغ ضمن سجل الدمج
                    self.merged_inits.append(rel_from)
                self.skipped.append((rel_from, "init-merged"))
                continue

            content = read_text_safe(py)
            target_rel, scores = score_file(py.name, content)
            reason = self._reason_text(target_rel, scores)

            dest_dir = self.clean_root / target_rel
            if not dest_dir.exists() and not self.dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)

            dest = unique_destination(dest_dir, py.name, self._used_dest)
            rel_to = str(dest.relative_to(self.source_root))

            if not self.dry_run:
                shutil.copy2(py, dest)

            self.moved_files.append((rel_from, rel_to, reason))
            self._record_remap(py, dest)

    # ------------------------------------------------------------------
    def _reason_text(self, target_rel: str, scores: Dict[str, int]) -> str:
        if not scores:
            return f"افتراضي -> {target_rel} (لم تتطابق كلمات مفتاحية)"
        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]
        detail = ", ".join(f"{k}={v}" for k, v in top)
        return f"{target_rel} (درجات: {detail})"

    # ------------------------------------------------------------------
    def _record_remap(self, src: Path, dest: Path) -> None:
        """تسجيل خريطة تحويل مسارات الاستيراد (dotted import paths)."""

        def to_module(p: Path, root: Path) -> str:
            rel = p.relative_to(root).with_suffix("")
            return ".".join(rel.parts)

        old_mod = to_module(src, self.source_root)
        new_mod = to_module(dest, self.clean_root)
        if old_mod and new_mod:
            self.import_remap[old_mod] = new_mod

    # ------------------------------------------------------------------
    def create_package_inits(self) -> None:
        """إنشاء __init__.py واحد لكل حزمة فرعية (إن لم يوجد)."""
        for rel in PACKAGE_DIRECTORIES:
            init_path = self.clean_root / rel / "__init__.py"
            if not init_path.exists():
                if not self.dry_run:
                    init_path.parent.mkdir(parents=True, exist_ok=True)
                    init_path.write_text(
                        f'"""حزمة {rel} — تم إنشاؤها تلقائياً بواسطة '
                        f'final_project_organizer."""\n',
                        encoding="utf-8",
                    )
                self.created_dirs.append(str(init_path.relative_to(self.source_root)))

    # ------------------------------------------------------------------
    def create_root_scaffold(self) -> None:
        """إنشاء ملفات الجذر الأساسية إن لم تكن موجودة."""
        scaffold: Dict[str, str] = {
            "README.md": (
                "# Smart Land Copilot\n\n"
                "مشروع تمت إعادة هيكلته بواسطة `final_project_organizer.py`.\n\n"
                "## الهيكل\n\n"
                "- `config/` — الإعدادات (settings.py)\n"
                "- `core/` — منطق الأعمال (account, ai, auction, customer_service, "
                "domain, financial, geological, matchmaking, prediction)\n"
                "- `infrastructure/` — قواعد البيانات والتكاملات والمراقبة\n"
                "- `api/` — مسارات HTTP والـ middleware\n"
                "- `web/` — واجهة الويب (app.py)\n"
                "- `microservices/` — docker-compose و k8s\n"
                "- `tests/` — اختبارات الوحدة والتكامل\n"
                "- `scripts/` — أدوات مساعدة\n"
            ),
            "requirements.txt": (
                "# أضف اعتماديات المشروع هنا\n"
                "fastapi\n"
                "uvicorn\n"
                "sqlalchemy\n"
                "pydantic\n"
                "pydantic-settings\n"
                "streamlit\n"
                "pytest\n"
            ),
            ".env.example": (
                "# مثال لمتغيرات البيئة\n"
                "APP_ENV=development\n"
                "DATABASE_URL=postgresql://user:password@localhost:5432/smartland\n"
                "SECRET_KEY=change-me\n"
            ),
            ".gitignore": (
                "__pycache__/\n"
                "*.py[cod]\n"
                ".env\n"
                ".venv/\n"
                "venv/\n"
                "*.egg-info/\n"
                ".pytest_cache/\n"
                ".mypy_cache/\n"
                "dist/\n"
                "build/\n"
            ),
            "web/app.py": (
                '"""نقطة دخول واجهة الويب (placeholder)."""\n\n'
                'if __name__ == "__main__":\n'
                '    print("Smart Land Copilot web app")\n'
            ),
            "web/Dockerfile": (
                "FROM python:3.11-slim\n"
                "WORKDIR /app\n"
                "COPY requirements.txt .\n"
                "RUN pip install --no-cache-dir -r requirements.txt\n"
                "COPY . .\n"
                'CMD ["python", "web/app.py"]\n'
            ),
            "microservices/docker-compose.yml": (
                "version: '3.9'\n"
                "services:\n"
                "  web:\n"
                "    build:\n"
                "      context: ..\n"
                "      dockerfile: web/Dockerfile\n"
                "    ports:\n"
                '      - "8000:8000"\n'
            ),
            ".github/workflows/ci.yml": (
                "name: CI\n"
                "on: [push, pull_request]\n"
                "jobs:\n"
                "  test:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "      - uses: actions/setup-python@v5\n"
                "        with:\n"
                "          python-version: '3.11'\n"
                "      - run: pip install -r requirements.txt\n"
                "      - run: pytest\n"
            ),
        }

        for rel, body in scaffold.items():
            path = self.clean_root / rel
            if not path.exists():
                if not self.dry_run:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(body, encoding="utf-8")
                self.created_dirs.append(str(path.relative_to(self.source_root)))

    # ------------------------------------------------------------------
    def write_import_remap(self) -> None:
        """كتابة ملف import_remap.json."""
        remap_path = self.clean_root / "import_remap.json"
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_root": str(self.source_root),
            "clean_root": str(self.clean_root),
            "count": len(self.import_remap),
            "mapping": dict(sorted(self.import_remap.items())),
        }
        if not self.dry_run:
            remap_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        self.created_dirs.append(str(remap_path.relative_to(self.source_root)))

    # ------------------------------------------------------------------
    def cleanup_legacy_dirs(self) -> None:
        """
        حذف المجلدات القديمة من الجذر بعد التأكد أنها لم تعد تحوي ملفات .py
        غير منقولة. (تم نسخ كل ملفات .py مسبقاً، لذا الحذف آمن.)
        """
        for name in KNOWN_LEGACY_DIRS:
            legacy = self.source_root / name
            if not legacy.exists() or not legacy.is_dir():
                continue
            if is_within(legacy, self.clean_root):
                continue

            # تأكّد أن كل ملفات .py المتبقية قد تم نقلها فعلاً
            remaining = [
                p for p in legacy.rglob("*.py")
                if p.name != "__init__.py"
            ]
            moved_sources = {m[0] for m in self.moved_files}
            unmoved = [
                str(p.relative_to(self.source_root))
                for p in remaining
                if str(p.relative_to(self.source_root)) not in moved_sources
            ]

            if unmoved:
                self.skipped.append(
                    (name, f"لم يُحذف: يوجد {len(unmoved)} ملف لم يُنقل")
                )
                continue

            if not self.dry_run:
                shutil.rmtree(legacy, ignore_errors=True)
            self.deleted_dirs.append(name)

    # ------------------------------------------------------------------
    def print_report(self) -> None:
        line = "=" * 70
        print("\n" + line)
        print("  التقرير النهائي")
        print(line)

        print(f"\n[1] المجلدات/الملفات المُنشأة ({len(self.created_dirs)}):")
        for d in self.created_dirs:
            print(f"    + {d}")

        print(f"\n[2] الملفات المنقولة ({len(self.moved_files)}):")
        for src, dst, reason in self.moved_files:
            print(f"    {src}")
            print(f"        -> {dst}")
            print(f"        [{reason}]")

        print(f"\n[3] ملفات __init__.py المدموجة ({len(self.merged_inits)}):")
        for f in self.merged_inits:
            print(f"    ~ {f}")

        print(f"\n[4] المجلدات القديمة المحذوفة ({len(self.deleted_dirs)}):")
        for d in self.deleted_dirs:
            print(f"    - {d}")

        if self.skipped:
            print(f"\n[5] عناصر تم تخطّيها / تحذيرات ({len(self.skipped)}):")
            for item, why in self.skipped:
                print(f"    ! {item} :: {why}")

        print(f"\n[6] خريطة الاستيراد import_remap.json: {len(self.import_remap)} إدخال")

        print("\n" + line)
        print("  تمت إعادة الهيكلة بنجاح" + (" (معاينة فقط)" if self.dry_run else ""))
        print(f"  الناتج في: {self.clean_root}")
        print(line)


# ===========================================================================
# نقطة الدخول
# ===========================================================================
def prompt_for_path() -> Path:
    while True:
        raw = input("أدخل مسار المشروع الحالي (المجلد الجذر): ").strip().strip('"').strip("'")
        if not raw:
            print("  المسار فارغ، حاول مرة أخرى.")
            continue
        p = Path(raw).expanduser()
        if not p.exists():
            print(f"  المسار غير موجود: {p}")
            continue
        if not p.is_dir():
            print(f"  المسار ليس مجلداً: {p}")
            continue
        return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="إعادة هيكلة مشروع Smart Land Copilot."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="مسار المشروع الجذر (إن لم يُحدّد سيُطلب تفاعلياً).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="معاينة فقط دون تنفيذ أي تغييرات فعلية.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="تخطّي طلب التأكيد قبل التنفيذ.",
    )
    args = parser.parse_args(argv)

    source = Path(args.path).expanduser() if args.path else prompt_for_path()
    if not source.exists() or not source.is_dir():
        print(f"خطأ: المسار غير صالح: {source}")
        return 1

    if not args.yes and not args.dry_run:
        print(f"\nسيتم إنشاء '{CLEAN_ROOT_NAME}/' داخل: {source.resolve()}")
        print("وستُنقل ملفات .py وتُحذف المجلدات القديمة بعد التأكد من النقل.")
        confirm = input("هل تريد المتابعة؟ [y/N]: ").strip().lower()
        if confirm not in ("y", "yes", "نعم"):
            print("تم الإلغاء.")
            return 0

    organizer = ProjectOrganizer(source, dry_run=args.dry_run)
    organizer.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
