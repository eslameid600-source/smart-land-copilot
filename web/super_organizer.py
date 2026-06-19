#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║           Smart Land Copilot — Super Organizer v1.0                ║
║  ينظّم كل ملفات المشروع في 5 مجلدات كبرى بضغطة زر واحدة          ║
╚══════════════════════════════════════════════════════════════════════╝

الهيكل الخماسي الصارم:
  1. core/land/          → بيانات الأراضي، الخرائط، AAA، المزايدات
  2. core/matchmaking/   → خوارزميات التوافق، تصنيفات المشترين، الحسابات
  3. core/rag/           → نماذج AI، محرك الاسترجاع، GLM، التنبؤ
  4. infrastructure/     → DevOps، Docker، قواعد البيانات، الـ ETL
  5. web/streamlit_app/  → واجهة المستخدم، السايدبار العربي، الشات

الاستخدام:
  python super_organizer.py              # وضع المعاينة (dry-run)
  python super_organizer.py --apply      # تنفيذ فعلي
  python super_organizer.py --apply --clean  # تنفيذ + حذف المجلدات القديمة
"""

import os
import sys
import shutil
import hashlib
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
# إعدادات رئيسية
# ═══════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parent
TARGET_FOLDERS = {
    "core/land": "بيانات الأراضي، الخرائط التفاعلية، تصنيفات AAA، المزايدات، الجيولوجيا",
    "core/matchmaking": "خوارزميات التوافق، تصنيفات المشترين، الحسابات المالية، نقاط الولاء",
    "core/rag": "نماذج AI، محرك الاسترجاع الذكي، GLM، Ollama، TFT، التنبؤات",
    "infrastructure": "DevOps، Docker، K8s، قواعد البيانات، الـ API، الدفع، المراقبة، الإعدادات",
    "web/streamlit_app": "واجهة Streamlit، السايدبار العربي، الشات المرئي",
}

# كلمات مفتاحية لتصنيف كل ملف → المجلد المناسب
# الترتيب مهم: نتحقق من الأعلى للأسفل
KEYWORD_RULES = [
    # ═══════ 1. core/land/ ═══════
    {
        "folder": "core/land",
        "keywords": [
            "land_database", "land_service", "search_engine",
            "soil_service", "groundwater_service", "geological", "gee_client", "egsma_reader",
            "land.py", "shared_models",  # ملف الـ API route للأراضي
        ],
        "path_patterns": [
            "geological/", "core/geological/",
            "data/land_database",
            "core/domain/land_database",
            "microservices/land-service/",
        ],
    },

    # ═══════ 2. core/matchmaking/ ═══════
    {
        "folder": "core/matchmaking",
        "keywords": [
            "matchmaking", "account_store", "account-service",
            "financial", "loyalty", "wallet", "investor", "landowner",
            "account.py",  # API route للحسابات
        ],
        "path_patterns": [
            "core/matchmaking/",
            "core/account/",
            "core/financial/",
            "microservices/account-service/",
        ],
    },

    # ═══════ 3. core/rag/ ═══════
    {
        "folder": "core/rag",
        "keywords": [
            "glm_client", "ollama_service", "llm_router", "tft_model", "tft_training",
            "tft_airflow", "prediction", "rag_chatbot", "chatbot",
            "airflow_dag",
        ],
        "path_patterns": [
            "ai/", "core/ai/",
            "core/prediction/",
            "microservices/prediction-service/",
            "customer_service/rag_chatbot",
            "core/customer_service/rag_chatbot",
        ],
    },

    # ═══════ 4. web/streamlit_app/ ═══════
    {
        "folder": "web/streamlit_app",
        "keywords": [
            "streamlit",
        ],
        "path_patterns": [
            "web/",
        ],
    },

    # ═══════ 5. infrastructure/ (الافتراضي لكل ما لم يُصنّف) ═══════
    {
        "folder": "infrastructure",
        "keywords": [
            "docker", "kong", "k8s", "kubernetes", "prometheus", "grafana",
            "sentry", "metrics", "monitoring", "alert",
            "fawry", "stripe", "payment", "transaction",
            "settings.py", ".env", "requirements.txt",
            "auth-service", "api-gateway",
            "Dockerfile", "docker-compose",
            "refactor_imports", "consolidate_code",
            "middleware", "routes/auth",
            "whatsapp", "zendesk", "hub.py", "survey_service",
        ],
        "path_patterns": [
            "config/", "infrastructure/",
            "microservices/shared/",
            "microservices/monitoring/",
            "microservices/api-gateway/",
            "microservices/auth-service/",
            "microservices/k8s/",
            "payment/",
            "api/",
            "customer_service/",
            "core/customer_service/",
            "scripts/",
        ],
    },
]

# الملفات الجذرية → التصنيف اليدوي
ROOT_FILE_MAPPING = {
    "app.py": "web/streamlit_app",
    "search_engine.py": "core/land",
    "requirements.txt": "infrastructure",
    ".env.example": "infrastructure",
    "Dockerfile.streamlit": "web/streamlit_app",
    "docker-compose-ollama.yml": "infrastructure",
    "refactor_imports.py": "infrastructure",
    "worklog.md": "infrastructure",
    "GITHUB_PROJECT_OVERVIEW.md": "infrastructure",
    "Smart_Land_Copilot_All_Code.txt": "infrastructure",
    "Smart_Land_Copilot_Vision_Product_Overview.html": "infrastructure",
    "Smart_Land_Copilot_Vision_Product_Overview.pdf": "infrastructure",
}


# ═══════════════════════════════════════════════════════════════
# دوال مساعدة
# ═══════════════════════════════════════════════════════════════

def file_hash(filepath: Path) -> str:
    """حساب hash للملف لرصد التكرار."""
    h = hashlib.md5(usedforsecurity=False)
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def classify_file(rel_path: str, filename: str) -> str:
    """
    تصنيف ملف واحد بناءً على اسمه ومساره.
    يُرجع اسم المجلد الهدف (مثل: "core/land").
    """
    rel_lower = rel_path.lower().replace("\\", "/")
    name_lower = filename.lower()

    # 0) ملفات DevOps دائماً في infrastructure بغض النظر عن المسار
    INFRA_OVERRIDE_NAMES = {
        "dockerfile", "requirements.txt", "dockerfile.streamlit",
    }
    if name_lower in INFRA_OVERRIDE_NAMES or filename.startswith("docker-compose"):
        return "infrastructure"

    # 0.5) ملفات K8s/YAML دائماً في infrastructure
    if filename.endswith((".yaml", ".yml")) and "k8s" in rel_lower:
        return "infrastructure"

    # 1) تحقق أولاً من الملفات الجذرية المعروفة
    if filename in ROOT_FILE_MAPPING:
        return ROOT_FILE_MAPPING[filename]

    # 2) تحقق من الكلمات المفتاحية وأنماط المسارات
    for rule in KEYWORD_RULES:
        # تحقق من أنماط المسار أولاً (أدق)
        for pattern in rule["path_patterns"]:
            if pattern.lower() in rel_lower:
                return rule["folder"]

        # تحقق من الكلمات المفتاحية في اسم الملف
        for kw in rule["keywords"]:
            if kw.lower() in name_lower:
                return rule["folder"]

    # 3) الافتراضي: infrastructure
    return "infrastructure"


def collect_all_files(project_root: Path) -> list[tuple[Path, str]]:
    """
    جمع كل الملفات القابلة للنقل (باستثناء السكريبت نفسه والمجلدات الهدف).
    يُرجع قائمة: [(مسار_كامل, مسار_نسبي), ...]
    """
    skip_dirs = {
        "core__land", "core__matchmaking", "core__rag",
        "infrastructure__backup", "web__streamlit_app",
        "_organized_backup", ".git", "__pycache__", "node_modules",
    }
    # نتجنب أيضاً مجلدات الهدف أثناء التجميع
    target_dirs_prefixes = ["core/land", "core/matchmaking", "core/rag"]

    all_files = []
    for root, dirs, files in os.walk(project_root):
        root_path = Path(root)
        rel = root_path.relative_to(project_root)
        rel_str = str(rel).replace("\\", "/")

        # تخطي المجلدات المحظورة
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]

        # تخطي مجلدات الهدف إذا وُجدت (لا نعيد جمع ما نُقل بالفعل)
        if any(rel_str.startswith(t) for t in target_dirs_prefixes):
            continue

        for f in files:
            # تخطي السكريبت نفسه
            if f == "super_organizer.py":
                continue
            # تخطي ملفات __pycache__
            if f.endswith(".pyc") or f.endswith(".pyo"):
                continue
            full_path = root_path / f
            all_files.append((full_path, rel_str + "/" + f if rel_str != "." else f))

    return all_files


def deduplicate_files(file_groups: dict) -> dict:
    """
    إزالة التكرار: إذا وُجد ملفان بنفس المحتوى (نفس hash)،
    نحتفظ بالأحدث أو بالأقصر مسار.
    """
    hash_groups = defaultdict(list)
    for target, files in file_groups.items():
        for fp, rp in files:
            h = file_hash(fp)
            if h:
                hash_groups[h].append((target, fp, rp))

    duplicates_to_skip = set()
    for h, group in hash_groups.items():
        if len(group) <= 1:
            continue
        # فرز: الأقصر مسار أولاً (الملف الأصل قبل النسخة)
        group.sort(key=lambda x: (len(x[2]), x[1].stat().st_mtime), reverse=False)
        # نحتفظ بالأول ونخطي الباقي
        for item in group[1:]:
            duplicates_to_skip.add(item[1])

    return duplicates_to_skip


def get_unique_filename(target_dir: Path, filename: str) -> Path:
    """
    إذا وُجد ملف بنفس الاسم في المجلد الهدف، نضيف رقم مميز.
    """
    target_path = target_dir / filename
    if not target_path.exists():
        return target_path

    stem = target_path.stem
    suffix = target_path.suffix
    counter = 2
    while True:
        new_name = f"{stem}_v{counter}{suffix}"
        new_path = target_dir / new_name
        if not new_path.exists():
            return new_path
        counter += 1


# ═══════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Smart Land Copilot — Super Organizer: ينظم 260 ملف في 5 مجلدات"
    )
    parser.add_argument("--apply", action="store_true",
                        help="تنفيذ النقل الفعلي (بدونها = معاينة فقط)")
    parser.add_argument("--clean", action="store_true",
                        help="حذف المجلدات القديمة الفارغة بعد النقل")
    parser.add_argument("--dry-run", action="store_true",
                        help="معاينة فقط (افتراضي)")
    args = parser.parse_args()

    is_dry_run = not args.apply
    is_clean = args.clean and not is_dry_run

    print("=" * 70)
    print("  Smart Land Copilot — Super Organizer v1.0")
    print("  " + ("🔍 وضع المعاينة (DRY-RUN)" if is_dry_run else "⚡ وضع التنفيذ الفعلي (APPLY)"))
    print("=" * 70)
    print()

    # ─── الخطوة 1: جمع كل الملفات ───
    print("📂 الخطوة 1/5: جمع كل الملفات...")
    all_files = collect_all_files(PROJECT_ROOT)
    print(f"   ✅ وُجد {len(all_files)} ملفاً")
    print()

    # ─── الخطوة 2: تصنيف كل ملف ───
    print("🏷️  الخطوة 2/5: تصنيف الملفات حسب الكلمات المفتاحية...")
    file_groups = defaultdict(list)  # target_folder -> [(full_path, rel_path), ...]
    unclassified = []

    for full_path, rel_path in all_files:
        filename = full_path.name
        target = classify_file(rel_path, filename)
        file_groups[target].append((full_path, rel_path))

    # طباعة ملخص التصنيف
    for folder, desc in TARGET_FOLDERS.items():
        count = len(file_groups.get(folder, []))
        print(f"   📁 {folder:25s} → {count:3d} ملف  | {desc}")

    others = [k for k in file_groups if k not in TARGET_FOLDERS]
    if others:
        for o in others:
            print(f"   ⚠️  {o:25s} → {len(file_groups[o]):3d} ملف  (غير مصنّف)")
    print()

    # ─── الخطوة 3: إزالة التكرار ───
    print("🔍 الخطوة 3/5: كشف الملفات المكررة ونزعها...")
    dupes_to_skip = deduplicate_files(file_groups)
    print(f"   ✅ وُجد {len(dupes_to_skip)} ملفاً مكرراً سيتم تخطيه")
    print()

    # ─── الخطوة 4: إنشاء المجلدات الهدف ───
    print("🏗️  الخطوة 4/5: إنشاء الهيكل الخماسي...")
    created_dirs = set()
    for folder in list(TARGET_FOLDERS.keys()) + others:
        target_dir = PROJECT_ROOT / folder.replace("/", os.sep)
        needs_create = not target_dir.exists()
        if needs_create:
            if not is_dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)
            created_dirs.add(folder)
        prefix = "سيُنشأ" if is_dry_run else "تم إنشاء"
        if needs_create:
            print(f"   {'📌' if is_dry_run else '✅'} {prefix}: {folder}/")
        # إنشاء __init__.py لكل مجلد Python
        init_file = target_dir / "__init__.py"
        needs_init = folder.startswith("core/") and not init_file.exists()
        if needs_init:
            if not is_dry_run:
                init_file.write_text("# Smart Land Copilot - {}\n".format(folder), encoding="utf-8")
            print(f"   {'📌' if is_dry_run else '✅'} {prefix}: {folder}/__init__.py")

    # __init__.py للمجلدات الأب
    for parent in ["core", "web"]:
        parent_dir = PROJECT_ROOT / parent
        parent_init = parent_dir / "__init__.py"
        if parent_dir.exists() and not parent_init.exists():
            if not is_dry_run:
                parent_init.write_text("# Smart Land Copilot - {}\n".format(parent), encoding="utf-8")
            print(f"   ✅ إنشاء: {parent}/__init__.py")
    print()

    # ─── الخطوة 5: نقل الملفات ───
    print("🚚 الخطوة 5/5: نقل الملفات إلى مجلداتها...")
    moved_count = 0
    skipped_dupes = 0
    skipped_same = 0

    for target_folder, files in sorted(file_groups.items()):
        target_dir = PROJECT_ROOT / target_folder.replace("/", os.sep)
        print(f"\n   📁 {target_folder}/")

        for full_path, rel_path in sorted(files, key=lambda x: x[1]):
            filename = full_path.name

            # تخطي المكررات
            if full_path in dupes_to_skip:
                skipped_dupes += 1
                print(f"      ⏭️  تخطي (مكرر): {filename}")
                continue

            # تخطي إذا كان الملف أصلاً في المجلد الهدف
            if full_path.parent == target_dir:
                skipped_same += 1
                print(f"      ✅ موجود مسبقاً: {filename}")
                continue

            # تحديد اسم فريد في المجلد الهدف
            dest = get_unique_filename(target_dir, filename)
            dest_rel = dest.relative_to(PROJECT_ROOT)

            if is_dry_run:
                print(f"      📋 سيُنقل: {rel_path} → {dest_rel}")
            else:
                try:
                    shutil.copy2(str(full_path), str(dest))
                    moved_count += 1
                    print(f"      ✅ نُسخ: {filename} → {dest_rel}")
                except Exception as e:
                    print(f"      ❌ خطأ في نسخ {filename}: {e}")

    # ─── الملخص النهائي ───
    print()
    print("=" * 70)
    print("  📊 ملخص العملية")
    print("=" * 70)
    print(f"   إجمالي الملفات المكتشفة:  {len(all_files)}")
    print(f"   الملفات المنقولة/المنسوخة: {moved_count}")
    print(f"   المكررات المتخطاة:         {skipped_dupes}")
    print(f"   الموجودة مسبقاً:           {skipped_same}")
    print(f"   المجلدات المُنشأة:         {len(created_dirs)}")
    print(f"   الوضع:                     {'🔍 معاينة فقط' if is_dry_run else '⚡ تم التنفيذ'}")
    print()

    if is_dry_run:
        print("  ⚡ لتشغيل التنفيذ الفعلي، أضف --apply:")
        print("     python super_organizer.py --apply")
        print()
        print("  🗑️  لحذف المجلدات القديمة الفارغة أيضاً:")
        print("     python super_organizer.py --apply --clean")
    else:
        print("  ✅ تم التنفيذ بنجاح!")
        if is_clean:
            print("  🗑️  جاري حذف المجلدات القديمة الفارغة...")
            _clean_empty_dirs(PROJECT_ROOT, TARGET_FOLDERS)
        print()
        print("  ⚠️  تنبيه: الملفات نُسخت (لم تُحذف من مكانها القديم).")
        print("     راجع النتيجة ثم احذف المجلدات القديمة يدوياً إذا اقتضى الأمر.")

    print("=" * 70)


def _clean_empty_dirs(root: Path, keep_folders: dict):
    """حذف المجلدات الفارغة التي ليست من المجلدات الخمسة الهدف."""
    keep_set = {str(root / k.replace("/", os.sep)) for k in keep_folders}
    # نحافظ أيضاً على core/ و web/ كآباء
    keep_set.add(str(root / "core"))
    keep_set.add(str(root / "web"))
    keep_set.add(str(root / "infrastructure"))

    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        dp = Path(dirpath)
        if str(dp) in keep_set:
            continue
        if not os.listdir(dirpath):  # فارغ
            try:
                os.rmdir(dirpath)
                print(f"   🗑️  حُذف: {dp.relative_to(root)}")
            except OSError:
                pass


if __name__ == "__main__":
    main()