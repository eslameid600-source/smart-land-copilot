#!/usr/bin/env python3
"""
purchase_module_scanner.py
==========================
سكريبت لاكتشاف واستبدال استيرادات `purchase_module` المكسورة.

المهام:
    1. يبحث في كل ملفات *.py عن `import purchase_module` أو `from purchase_module...`
    2. يتحقق إن كان الموديول موجودًا فعليًا (قابل للاستيراد)
    3. ينشئ تقريرًا errors.txt يضم: اسم الملف + رقم السطر + نص الاستيراد
    4. يستبدل الاستيراد بكود بديل (خريطة استبدال مدمجة افتراضياً داخل الكود)

خريطة الاستبدال الافتراضية (DEFAULT_REPLACEMENT_MAP):
    مدمجة في السكريبت — لا تحتاج أي ملفات JSON خارجية.
    يمكن تجاوزها عبر --map-file أو --replacement لو أردت.

الاستخدام:
    # 1. فحص فقط + إنشاء errors.txt
    python3 purchase_module_scanner.py scan /path/to/project

    # 2. الفحص + الاستبدال الفوري بخريطة الاستبدال المدمجة (الوضع الافتراضي الموصى به)
    python3 purchase_module_scanner.py fix /path/to/project

    # 3. معاينة الاستبدالات قبل التطبيق (dry-run)
    python3 purchase_module_scanner.py fix /path/to/project --dry-run

    # 4. تجاوز الخريطة المدمجة بسطر موحّد
    python3 purchase_module_scanner.py fix /path/to/project \
        --replacement "from api.routes.account_store import *" --no-default-map

    # 5. تجاوز الخريطة المدمجة بملف JSON مخصص
    python3 purchase_module_scanner.py fix /path/to/project \
        --map-file replacements.json --no-default-map

شروط الاستبدال:
    - الاستبدال يحدث فقط للأسطر التي تشير إلى موديول غير موجود فعليًا
    - يتم حفظ نسخة احتياطية .bak قبل أي تعديل
    - يقيس success/failure counts ويطبعها في النهاية

Author: Super Z
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────
# خريطة الاستبدال الافتراضية المدمجة (BUILT-IN DEFAULT MAP)
# ──────────────────────────────────────────────────────────────
# كل مفتاح = مسار موديول purchase_module قديم
# كل قيمة = سطر الاستيراد البديل الجديد (بدون المسافة البادئة — تُضاف تلقائياً)
#
# القاعدة: نُعيد التصدير من المواقع الفعلية في المشروع:
#   - api.routes.* للمسارات والخدمات
#   - core.account.* للنماذج والـ repositories
#   - core.domain للـ schemas المركزية
#   - infrastructure.database للاتصال بقاعدة البيانات
#
# يمكنك تعديل هذه القيم مباشرةً هنا لتغيير سلوك الاستبدال الافتراضي.
# ──────────────────────────────────────────────────────────────

DEFAULT_REPLACEMENT_MAP: Dict[str, str] = {
    # الجذر
    "purchase_module":
        "from api.routes.account_store import *  # noqa: F401,F403",

    # النماذج (ORM models)
    "purchase_module.models":
        "from core.account.models import *  # noqa: F401,F403",

    # الـ schemas (Pydantic)
    "purchase_module.schemas":
        "from core.domain import *  # noqa: F401,F403",

    # المصادقة
    "purchase_module.auth":
        "from api.routes.auth import *  # noqa: F401,F403",

    # قاعدة البيانات
    "purchase_module.database":
        "from infrastructure.database import get_db, get_session, Base  # noqa: F401",

    # المسارات (routers)
    "purchase_module.routers":
        "from api.routes.investor_router import router as investors_router  # noqa: F401\n"
        "from api.routes.landowner_router import router as landowners_router  # noqa: F401\n"
        "from api.routes.transfer_router import router as payments_router  # noqa: F401",

    # خدمات المستثمر
    "purchase_module.services.investor_service":
        "from core.account.investor_service import *  # noqa: F401,F403",

    # خدمات مالك الأرض
    "purchase_module.services.landowner_service":
        "from core.account.investor_service import *  # noqa: F401,F403",

    # خدمات الحوافز
    "purchase_module.services.incentive_service":
        "from core.account.investor_service import calculate_incentive, redeem_loyalty_points  # noqa: F401",

    # اختبارات (conftest)
    "purchase_module.tests.conftest":
        "import pytest  # noqa: F401",
}

# استبدال افتراضي مُوحَّد يُطبَّق على أي مسار purchase_module.* غير موجود في الخريطة أعلاه
DEFAULT_FALLBACK_REPLACEMENT = "from api.routes.account_store import *  # noqa: F401,F403"


# ──────────────────────────────────────────────
# نموذج بيانات: سجل استيراد واحد
# ──────────────────────────────────────────────

@dataclass
class ImportOccurrence:
    """يمثل occurrence واحد لاستيراد purchase_module في ملف."""
    file_path: str
    line_number: int          # 1-indexed
    line_text: str            # النص الكامل للسطر
    import_kind: str          # "import" أو "from"
    module_path: str          # "purchase_module" أو "purchase_module.services"
    imported_names: List[str] = field(default_factory=list)  # للأسماء المستوردة في `from ... import a, b, c`
    module_exists: bool = False
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "file": self.file_path,
            "line": self.line_number,
            "kind": self.import_kind,
            "module": self.module_path,
            "imported_names": self.imported_names,
            "exists": self.module_exists,
            "error": self.error_message,
            "text": self.line_text.rstrip(),
        }


# ──────────────────────────────────────────────
# الماسح الرئيسي
# ──────────────────────────────────────────────

class PurchaseModuleScanner:
    """يبحث عن استيرادات purchase_module ويتحقق من وجودها."""

    # نمط Regex لاستيرادات purchase_module
    # يدعم: import purchase_module
    #        import purchase_module.submodule as alias
    #        from purchase_module import x, y
    #        from purchase_module.submodule import (a, b, c)
    PATTERNS = [
        # import purchase_module[.submodule...] [as alias]
        re.compile(
            r'^(\s*)import\s+(purchase_module(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)'
            r'(?:\s+as\s+([a-zA-Z_][a-zA-Z0-9_]*))?\s*$'
        ),
        # from purchase_module[.submodule...] import ...
        re.compile(
            r'^(\s*)from\s+(purchase_module(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s+import\s+(.+?)\s*$'
        ),
    ]

    def __init__(
        self,
        project_root: str,
        verbose: bool = False,
        backup_ext: str = ".bak",
    ):
        self.project_root = Path(project_root).resolve()
        self.verbose = verbose
        self.backup_ext = backup_ext
        # أضف جذر المشروع إلى sys.path مؤقتًا للتحقق من الاستيراد
        if str(self.project_root) not in sys.path:
            sys.path.insert(0, str(self.project_root))

    # ─── فحص وجود موديول ───

    @staticmethod
    def _module_exists(module_name: str) -> Tuple[bool, str]:
        """يتحقق إن كان الموديول قابل للاستيراد. يعيد (exists, error_msg)."""
        try:
            # نستخدم find_spec بدلاً من import لتجنب الأعراض الجانبية
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                return False, f"ModuleNotFoundError: No module named '{module_name}'"
            return True, ""
        except ModuleNotFoundError as e:
            return False, f"ModuleNotFoundError: {e}"
        except ImportError as e:
            # قد يحدث هذا لو الموديول موجود لكنه فشل في الاستيراد (يعتبر "موجود" جزئيًا)
            return True, f"ImportError (exists but broken): {e}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    # ─── تحليل سطر واحد ───

    def _parse_line(self, line: str) -> Optional[Tuple[str, str, List[str], str]]:
        """يحلل سطرًا واحدًا. يعيد (kind, module_path, names, indent) أو None."""
        for pattern in self.PATTERNS:
            m = pattern.match(line)
            if not m:
                continue
            indent = m.group(1)
            if pattern is self.PATTERNS[0]:
                # import purchase_module...
                module_path = m.group(2)
                return ("import", module_path, [], indent)
            else:
                # from purchase_module... import ...
                module_path = m.group(2)
                imported = m.group(3).strip()
                # فصل الأسماء (تتعامل مع a, b, c أو (a, b, c))
                if imported.startswith("("):
                    imported = imported.strip("()")
                names = [n.strip() for n in imported.split(",") if n.strip()]
                return ("from", module_path, names, indent)
        return None

    # ─── فحص ملف واحد ───

    def scan_file(self, file_path: Path) -> List[ImportOccurrence]:
        """يفحص ملف .py واحد ويعيد قائمة بكل occurrence."""
        occurrences: List[ImportOccurrence] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            if self.verbose:
                print(f"  [skip] {file_path}: {e}")
            return occurrences

        for lineno, raw_line in enumerate(content.splitlines(), start=1):
            # تخطي التعليقات والأسطر الفارغة بسرعة
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # فحص سريع قبل تشغيل الـ regex
            if "purchase_module" not in stripped:
                continue
            parsed = self._parse_line(raw_line)
            if parsed is None:
                continue
            kind, module_path, names, _ = parsed
            exists, err = self._module_exists(module_path)
            occ = ImportOccurrence(
                file_path=str(file_path.relative_to(self.project_root)),
                line_number=lineno,
                line_text=raw_line,
                import_kind=kind,
                module_path=module_path,
                imported_names=names,
                module_exists=exists,
                error_message=err,
            )
            occurrences.append(occ)
        return occurrences

    # ─── فحص المشروع كامل ───

    def scan_project(self) -> List[ImportOccurrence]:
        """يفحص كل ملفات *.py في المشروع ويعيد كل occurrence."""
        all_occurrences: List[ImportOccurrence] = []
        py_files = sorted(self.project_root.rglob("*.py"))
        # استبعاد __pycache__
        py_files = [p for p in py_files if "__pycache__" not in p.parts]

        if self.verbose:
            print(f"Scanning {len(py_files)} Python files in {self.project_root}...")

        for path in py_files:
            occs = self.scan_file(path)
            if occs:
                all_occurrences.extend(occs)
                if self.verbose:
                    print(f"  [{path.relative_to(self.project_root)}] {len(occs)} occurrence(s)")

        return all_occurrences

    # ─── توليد التقرير ───

    @staticmethod
    def write_report(
        occurrences: List[ImportOccurrence],
        output_path: Path,
        only_broken: bool = True,
    ) -> None:
        """يكتب تقرير errors.txt."""
        rows = [o for o in occurrences if (not only_broken) or (not o.module_exists)]
        lines: List[str] = []
        lines.append("=" * 78)
        lines.append("تقرير استيرادات purchase_module المكسورة")
        lines.append("=" * 78)
        lines.append("")
        lines.append(f"إجمالي الاستيرادات المكتشفة: {len(occurrences)}")
        lines.append(f"الاستيرادات المكسورة (موديول غير موجود): {len(rows)}")
        lines.append("")
        lines.append("-" * 78)
        lines.append(f"{'الملف':<45} {'السطر':<6} {'النوع':<7} {'الموديول'}")
        lines.append("-" * 78)

        # تجميع حسب الملف لتحسين القراءة
        by_file: Dict[str, List[ImportOccurrence]] = {}
        for o in rows:
            by_file.setdefault(o.file_path, []).append(o)

        for file_path in sorted(by_file.keys()):
            for o in by_file[file_path]:
                lines.append(
                    f"{file_path:<45} {o.line_number:<6} {o.import_kind:<7} {o.module_path}"
                )
                lines.append(f"  → {o.line_text.strip()}")
                lines.append(f"  ⚠ {o.error_message}")
                lines.append("")

        lines.append("=" * 78)
        lines.append("نهاية التقرير")
        lines.append("=" * 78)

        output_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n[OK] التقرير محفوظ في: {output_path}")
        print(f"     إجمالي: {len(occurrences)} استيراد، {len(rows)} مكسور")


# ──────────────────────────────────────────────
# المستبدل (Replacer)
# ──────────────────────────────────────────────

class PurchaseModuleReplacer:
    """يستبدل استيرادات purchase_module المكسورة بكود بديل."""

    def __init__(
        self,
        scanner: PurchaseModuleScanner,
        replacement_map: Optional[Dict[str, str]] = None,
        default_replacement: Optional[str] = None,
        backup_ext: str = ".bak",
        dry_run: bool = False,
        use_fallback: bool = True,
    ):
        self.scanner = scanner
        # إذا لم تُمرّر خريطة، نستخدم الخريطة المدمجة افتراضياً
        self.replacement_map = replacement_map if replacement_map is not None else dict(DEFAULT_REPLACEMENT_MAP)
        self.default_replacement = default_replacement
        self.backup_ext = backup_ext
        self.dry_run = dry_run
        self.use_fallback = use_fallback

    def _build_replacement(
        self, occ: ImportOccurrence, indent: str
    ) -> Optional[str]:
        """يبني سطر الاستبدال لـ occurrence واحد.

        ترتيب الأولوية:
            1) مطابقة تامة في replacement_map (مفتاح = module_path كامل)
            2) مطابقة بادئة (module_path.startswith(prefix + "."))
            3) default_replacement إن وُجد (يُطبَّق على كل ما لم يُطابق)
            4) DEFAULT_FALLBACK_REPLACEMENT إن كان use_fallback=True
            5) لا يوجد استبدال متاح → None
        """
        module_path = occ.module_path

        # 1) محاولة المطابقة من replacement_map (match على module_path كامل)
        if module_path in self.replacement_map:
            return f"{indent}{self.replacement_map[module_path]}"

        # 2) مطابقة بادئة (مثلاً: "purchase_module.services.investor_service"
        #     يطابق المفتاح "purchase_module.services")
        #     نرتّب المفاتيح بطول تنازلي لتفضيل المطابقة الأطول (أكثر تحديدًا)
        for prefix in sorted(self.replacement_map.keys(), key=len, reverse=True):
            replacement = self.replacement_map[prefix]
            if module_path == prefix or module_path.startswith(prefix + "."):
                return f"{indent}{replacement}"

        # 3) default_replacement الصريح (من --replacement)
        if self.default_replacement:
            return f"{indent}{self.default_replacement}"

        # 4) fallback المدمج في الكود
        if self.use_fallback:
            return f"{indent}{DEFAULT_FALLBACK_REPLACEMENT}"

        # 5) لا يوجد استبدال متاح
        return None

    def replace_in_file(
        self, file_path: Path, occurrences: List[ImportOccurrence]
    ) -> Tuple[int, int, List[str]]:
        """يستبدل الأسطر في ملف واحد. يعيد (success_count, fail_count, messages)."""
        if not occurrences:
            return (0, 0, [])

        # التحقق من أن كل occurrence له استبدال متاح
        # (لو أي واحد ما له استبدال، نفشل الملف بأكمله لضمان التناسق)
        replacements: List[Tuple[int, str, str]] = []  # (lineno, original, replacement)
        for occ in occurrences:
            # نستخرج المسافة البادئة من النص الأصلي
            stripped = occ.line_text.lstrip()
            indent = occ.line_text[: len(occ.line_text) - len(stripped)]
            new_line = self._build_replacement(occ, indent)
            if new_line is None:
                msg = f"  [skip] {file_path}:{occ.line_number} — لا يوجد استبدال متاح لـ '{occ.module_path}'"
                return (0, 1, [msg])
            replacements.append((occ.line_number, occ.line_text, new_line))

        if self.dry_run:
            msgs = [f"  [dry-run] {file_path}:"]
            for lineno, orig, new in replacements:
                msgs.append(f"    line {lineno}:")
                msgs.append(f"      - {orig.rstrip()}")
                msgs.append(f"      + {new.rstrip()}")
            return (0, 0, msgs)

        # قراءة الملف
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return (0, 1, [f"  [error] {file_path}: {e}"])

        lines = content.splitlines(keepends=False)

        # تطبيق الاستبدالات (نعكس الترتيب لتفادي إزاحة أرقام الأسطر)
        for lineno, _orig, new_line in sorted(replacements, key=lambda x: -x[0]):
            if 1 <= lineno <= len(lines):
                lines[lineno - 1] = new_line

        new_content = "\n".join(lines)
        if content.endswith("\n"):
            new_content += "\n"

        # نسخة احتياطية
        backup_path = file_path.with_suffix(file_path.suffix + self.backup_ext)
        try:
            backup_path.write_text(content, encoding="utf-8")
        except Exception as e:
            return (0, 1, [f"  [error] فشل النسخة الاحتياطية {backup_path}: {e}"])

        # كتابة الملف المحدّث
        try:
            file_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return (0, 1, [f"  [error] فشل الكتابة {file_path}: {e}"])

        msgs = [f"  [ok] {file_path}: تم استبدال {len(replacements)} سطر"]
        return (len(replacements), 0, msgs)

    def replace_all(
        self, occurrences: List[ImportOccurrence]
    ) -> Tuple[int, int]:
        """ينفذ الاستبدال على كل الملفات. يعيد (total_success, total_fail)."""
        # تصفية: نستبدل فقط الاستيرادات المكسورة (module_exists = False)
        broken = [o for o in occurrences if not o.module_exists]
        # تجميع حسب الملف
        by_file: Dict[str, List[ImportOccurrence]] = {}
        for o in broken:
            by_file.setdefault(o.file_path, []).append(o)

        total_success = 0
        total_fail = 0

        print(f"\nاستبدال {len(broken)} استيراد مكسور في {len(by_file)} ملف...")
        if self.dry_run:
            print("[وضع dry-run — لن يتم تعديل أي ملف فعليًا]\n")
        else:
            print(f"[سيتم إنشاء نسخ احتياطية بامتداد {self.backup_ext}]\n")

        for rel_path in sorted(by_file.keys()):
            file_path = self.scanner.project_root / rel_path
            occs = by_file[rel_path]
            success, fail, msgs = self.replace_in_file(file_path, occs)
            total_success += success
            total_fail += fail
            for msg in msgs:
                print(msg)

        return (total_success, total_fail)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def cmd_scan(args: argparse.Namespace) -> int:
    """وضع scan: فحص + إنشاء errors.txt."""
    scanner = PurchaseModuleScanner(
        project_root=args.project,
        verbose=args.verbose,
    )
    occurrences = scanner.scan_project()
    scanner.write_report(occurrences, Path(args.output), only_broken=True)

    # طباعة ملخص على الشاشة
    broken = [o for o in occurrences if not o.module_exists]
    print("\n" + "=" * 60)
    print("ملخص الفحص")
    print("=" * 60)
    print(f"المسح الضوئي:        {len(occurrences)} استيراد purchase_module")
    print(f"الموجود فعليًا:      {len(occurrences) - len(broken)}")
    print(f"المكسور (غير موجود): {len(broken)}")
    print(f"التقرير:             {args.output}")
    return 0 if not broken else 1  # exit code 1 لو فيه أخطاء (مفيد للـ CI)


def cmd_fix(args: argparse.Namespace) -> int:
    """وضع fix: فحص + استبدال.

    افتراضياً يستخدم الخريطة المدمجة DEFAULT_REPLACEMENT_MAP + fallback.
    يمكن تجاوزها عبر:
        --replacement <line>     : سطر موحّد لكل الاستيرادات
        --map-file <file>        : خريطة JSON خارجية
        --no-default-map         : تعطيل الخريطة المدمجة (يستخدم --replacement أو --map-file فقط)
        --no-fallback            : تعطيل fallback المدمج (الاستيرادات غير المطابوقة تُترك دون استبدال)
    """
    scanner = PurchaseModuleScanner(
        project_root=args.project,
        verbose=args.verbose,
    )
    occurrences = scanner.scan_project()

    # بناء replacement_map
    replacement_map: Optional[Dict[str, str]] = None

    # 1) إذا --no-default-map، نبدأ بخريطة فارغة (بدلاً من المدمجة)
    if args.no_default_map:
        replacement_map = {}
    else:
        replacement_map = dict(DEFAULT_REPLACEMENT_MAP)
        print(f"[info] استخدام الخريطة المدمجة ({len(replacement_map)} تعيين)")

    # 2) دمج --map-file إن وُجد (يتجاوز المدمج)
    if args.map_file:
        try:
            with open(args.map_file, encoding="utf-8") as f:
                external_map = json.load(f)
            replacement_map.update(external_map)
            print(f"[info] دمج {len(external_map)} تعيين من {args.map_file}")
        except Exception as e:
            print(f"[خطأ] فشل تحميل {args.map_file}: {e}")
            return 2

    # 3) --replacement يتجاوز كخيار fallback إضافي
    default_replacement = args.replacement
    if default_replacement:
        print(f"[info] استخدام استبدال موحّد: {default_replacement}")

    use_fallback = not args.no_fallback
    if use_fallback and not default_replacement:
        print(f"[info] fallback المدمج مُفعّل: {DEFAULT_FALLBACK_REPLACEMENT}")
    elif not use_fallback:
        print("[info] fallback المدمج مُعطّل — الاستيرادات غير المطابوقة لن تُستبدل")

    replacer = PurchaseModuleReplacer(
        scanner=scanner,
        replacement_map=replacement_map,
        default_replacement=default_replacement,
        backup_ext=args.backup_ext,
        dry_run=args.dry_run,
        use_fallback=use_fallback,
    )
    total_success, total_fail = replacer.replace_all(occurrences)

    # حفظ التقرير أيضًا
    scanner.write_report(occurrences, Path(args.output), only_broken=True)

    print("\n" + "=" * 60)
    print("ملخص الاستبدال")
    print("=" * 60)
    print(f"نجح: {total_success}   فشل: {total_fail}")
    print(f"التقرير: {args.output}")
    return 0 if total_fail == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="purchase_module_scanner",
        description="يكشف ويستبدل استيرادات purchase_module المكسورة في مشروع بايثون. "
                    "يحتوي على خريطة استبدال مدمجة افتراضياً — لا يحتاج أي ملفات إضافية.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
أمثلة:
  # 1. فحص فقط + تقرير errors.txt
  python3 purchase_module_scanner.py scan ./my_project

  # 2. الاستبدال الفوري بالخريطة المدمجة (الأنسب للاستخدام اليومي)
  python3 purchase_module_scanner.py fix ./my_project

  # 3. معاينة الاستبدالات قبل التطبيق (dry-run)
  python3 purchase_module_scanner.py fix ./my_project --dry-run

  # 4. استخدام سطر موحّد بدلاً من الخريطة المدمجة
  python3 purchase_module_scanner.py fix ./my_project \\
      --replacement "from api.routes.account_store import *" --no-default-map

  # 5. دمج خريطة مدمجة + خريطة خارجية (الخارجية تتجاوز المدمجة عند التعارض)
  python3 purchase_module_scanner.py fix ./my_project --map-file extra.json

  # 6. تعطيل fallback لترك الاستيرادات غير المطابوقة دون استبدال
  python3 purchase_module_scanner.py fix ./my_project --no-fallback

الخريطة المدمجة (DEFAULT_REPLACEMENT_MAP) تضم:
  purchase_module                     → from api.routes.account_store import *
  purchase_module.models              → from core.account.models import *
  purchase_module.schemas             → from core.domain import *
  purchase_module.auth                → from api.routes.auth import *
  purchase_module.database            → from infrastructure.database import get_db, get_session, Base
  purchase_module.routers             → investors/landowners/payments routers
  purchase_module.services.investor_service     → from core.account.investor_service import *
  purchase_module.services.landowner_service    → from core.account.investor_service import *
  purchase_module.services.incentive_service    → calculate_incentive, redeem_loyalty_points
  purchase_module.tests.conftest      → import pytest

يمكنك تعديل DEFAULT_REPLACEMENT_MAP داخل الكود مباشرة لتغيير السلوك الافتراضي.
""",
    )

    sub = parser.add_subparsers(dest="command", required=True, metavar="{scan,fix}")

    # ─── scan ───
    p_scan = sub.add_parser("scan", help="فحص فقط + إنشاء تقرير errors.txt")
    p_scan.add_argument("project", help="مسار جذر المشروع")
    p_scan.add_argument(
        "-o", "--output", default="errors.txt",
        help="مسار ملف التقرير (افتراضي: errors.txt)",
    )
    p_scan.add_argument("-v", "--verbose", action="store_true", help="مخرجات مفصلة")
    p_scan.set_defaults(func=cmd_scan)

    # ─── fix ───
    p_fix = sub.add_parser(
        "fix",
        help="فحص + استبدال الاستيرادات المكسورة. افتراضياً يستخدم الخريطة المدمجة.",
    )
    p_fix.add_argument("project", help="مسار جذر المشروع")
    p_fix.add_argument(
        "-o", "--output", default="errors.txt",
        help="مسار ملف التقرير",
    )
    p_fix.add_argument(
        "-r", "--replacement",
        help="سطر استبدال موحّد يُطبَّق على كل purchase_module.* (يتجاوز الخريطة)",
    )
    p_fix.add_argument(
        "-m", "--map-file",
        help="ملف JSON بخريطة استبدال خارجية (يُدمج مع المدمجة، أو يستخدم وحده مع --no-default-map)",
    )
    p_fix.add_argument(
        "--no-default-map", action="store_true",
        help="تعطيل الخريطة المدمجة DEFAULT_REPLACEMENT_MAP (استخدم --replacement أو --map-file فقط)",
    )
    p_fix.add_argument(
        "--no-fallback", action="store_true",
        help="تعطيل fallback المدمج — الاستيرادات غير المطابوقة تُترك دون استبدال",
    )
    p_fix.add_argument(
        "--backup-ext", default=".bak",
        help="امتداد النسخة الاحتياطية (افتراضي: .bak)",
    )
    p_fix.add_argument(
        "--dry-run", action="store_true",
        help="معاينة الاستبدالات دون تعديل الملفات فعليًا",
    )
    p_fix.add_argument("-v", "--verbose", action="store_true", help="مخرجات مفصلة")
    p_fix.set_defaults(func=cmd_fix)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
