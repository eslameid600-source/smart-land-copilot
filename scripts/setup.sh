#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
# Smart Land Management Copilot — سكربت التثبيت الشامل
# ══════════════════════════════════════════════════════════════
# الاستخدام:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh             # التثبيت كامل (Docker + Python + DB + تشغيل)
#   ./scripts/setup.sh --skip-docker   # تثبيت محلي بدون Docker
#   ./scripts/setup.sh --skip-db      # تخطي Docker وDB، ثبّت Python فقط
#   ./scripts/setup.sh --skip-python   # تخطي Python، Docker + DB فقط
# ════════════════════════════════════════════════════════════════
set -euo pipefail

# ─── ألوان الطرفية ───────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

STEP=0
next_step() {
    STEP=$((STEP + 1))
    echo ""
    echo -e "${CYAN}[$STEP/6] ${BOLD}$1${NC}"
}

info()  { echo -e "${GREEN}  ✓${NC} $*"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $*"; }
error() { echo -e "${RED}  ✗${NC} $*" >&2; exit 1; }

# ─── تحليل المعاملات ─────────────────────────────────────────────
SKIP_DOCKER=false
SKIP_DB=false
SKIP_PYTHON=false
SEED_DATA=false

for arg in "$@"; do
    case "$arg" in
        --skip-docker)   SKIP_DOCKER=true ;;
        --skip-db)      SKIP_DB=true ;;
        --skip-python)   SKIP_PYTHON=true ;;
        --seed)          SEED_DATA=true ;;
        --help|-h)
            echo "الاستخدام: $0 [خيارات]"
            echo "  --skip-docker   تخطي Docker"
            echo "  --skip-db      تخطي تهيئة قاعدة البيانات"
            echo "  --skip-python   تخطي تثبيت Python"
            echo "  --seed          إدخال بيانات تجريبية بعد التهيئة"
            echo "  --help          عرض المساعدة"
            exit 0
            ;;
    esac
done

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo ""
echo -e "${CYAN}${BOLD}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║  Smart Land Management Copilot — سكربت التثبيت الشامل              ║${NC}"
echo -e "${CYAN}${BOLD}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ═══════════════════════════════════════════════════════════
# الخطوة 1: Docker (PostgreSQL + Redis)
# ═══════════════════════════════════════════════════════════
if [ "$SKIP_DOCKER" = "false" ]; then
    next_step "Docker — تشغيل PostgreSQL و Redis"

    if ! command -v docker &>/dev/null; then
        error "Docker غير مثبّت. ثبّته أولاً: https://docs.docker.com/get-docker/"
    fi

    if docker compose -f docker-compose.db.yml ps 2>/dev/null | grep -q "Up\|running"; then
        info "  الحاويات تعمل بالفعل — تخطي إعادة التشغيل"
    else
        info "  تشغيل الحاويات..."
        docker compose -f docker-compose.db.yml up -d 2>&1
    fi

    # انتظار PostgreSQL
    info "  انتظار PostgreSQL..."
    RETRIES=15
    for i in $(seq 1 $RETRIES); do
        if docker compose -f docker-compose.db.yml exec -T postgres pg_isready -U smartland -d smartland &>/dev/null; then
            info "  PostgreSQL جاهز بعد ${i} محاولة"
            break
        fi
        sleep 2
        echo -ne "\r    محاولة $i/$RETRIES..."
    done
    echo ""

    if ! docker compose -f docker-compose.db.yml exec -T postgres pg_isready -U smartland -d smartland &>/dev/null; then
        error "PostgreSQL لم يصبح جاهزاً. تحقق: docker compose -f docker-compose.db.yml logs postgres"
    fi
fi

# ═══════════════════════════════════════════════════════════
# الخطوة 2: ملف .env
# ═══════════════════════════════════════════════════════════
next_step "ملف .env — متغيرات البيئة"

if [ ! -f ".env" ]; then
    if [ -f ".env.production" ]; then
        cp .env.production .env
        info "  تم نسخ .env.production → .env"
        warn "  ⚠ عدّل القيم الحساسة (GLM_API_KEY, JWT_SECRET) في .env!"
    else
        warn "  لا يوجد .env.production — إنشاء .env بقيم تطوير"
        cat > .env << 'INHERIT'
# ── التطبيق ──
APP_ENV=development
DEBUG=true
DATABASE_URL=postgresql+asyncpg://smartland:smartland123@localhost:5432/smartland
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=smartland
DATABASE_USER=smartland
DATABASE_PASSWORD=smartland123
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
JWT_SECRET=dev-secret-change-me
GLM_API_KEY=
GLM_BASE_URL=https://openrouter.ai/api/v1
GLM_MODEL=glm-5-turbo
OLLAMA_BASE_URL=http://localhost:11434
REDIS_URL=redis://localhost:6379/0
INHERIT
        info "  تم إنشاء .env بقيم تطوير"
    fi
else
    info "  ملف .env موجود بالفعل"
fi

# تحميل المتغيرات
set -a
source .env 2>/dev/null || true
set +a

# ═══════════════════════════════════════════════════════════
# الخطوة 3: تثبيت Python
# ═══════════════════════════════════════════════════════════
if [ "$SKIP_PYTHON" = "false" ]; then
    next_step "Python — تثبيت الحزم المطلوبة"

    # تحقق من وجود Python 3.11+
    if ! command -v python3 &>/dev/null; then
        error "Python 3 غير مثبّت. ثبّته: sudo apt install python3 python3-pip python3-venv"
    fi
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    info "  Python $PY_VER"

    # تحقق من وجود pip
    if ! command -v pip3 &>/dev/null && ! python3 -m pip --version &>/dev/null; then
        warn "  pip3 غير موجود — تثبيته..."
        python3 -m ensurepip --upgrade 2>&1 | tail -3
    fi

    # تثبيت الحزم
    info "  تثبيت الحزم من requirements.txt..."
    pip install --break-system-packages -r requirements.txt 2>&1 | tail -5

    # تحقق من الحزم الأساسية
    for pkg in sqlalchemy asyncpg alembic psycopg2 redis streamlit pandas scikit-learn; do
        python3 -c "import $pkg" 2>/dev/null || warn "  $pkg غير مثبّت (قد يحتاج pip install $pkg)"
    done
fi

# ═══════════════════════════════════════════════════════════
# الخطوة 4: إنشاء الجداول (Alembic / SQLAlchemy)
# ═══════════════════════════════════════════════════════════
if [ "$SKIP_DB" = "false" ]; then
    next_step "قاعدة البيانات — إنشاء الجداول"

    # انتظار اتصال PostgreSQL
    RETRIES=15
    for i in $(seq 1 $RETRIES); do
        if python3 -c "
import psycopg2
try:
    c = psycopg2.connect('host=localhost dbname=smartland user=smartland password=smartland123')
    c.close(); print('OK')
except: print('FAIL')
" 2>/dev/null | grep -q "OK"; then
            info "  اتصال PostgreSQL ناجح"
            break
        fi
        echo -ne "\r    انتظار $i/$RETRIES..."
        sleep 2
    done
    echo ""

    # تشغيل الترحيلات عبر init_db.sh
    chmod +x scripts/init_db.sh
    if [ "$SEED_DATA" = "true" ]; then
        bash scripts/init_db.sh --seed
    else
        bash scripts/init_db.sh
    fi
fi

# ═════════════════════════════════════════════════════════
# الخطوة 5: إنشاء مجل ML النموذج (اختياري)
# ═══════════════════════════════════════════════════════════
next_step "نظام ML — تدريب النموذج (اختياري)"

if command -v python3 &>/dev/null && python3 -c "import sklearn" 2>/dev/null; then
    ML_DIR="core/matchmaking/_ml_models"
    if [ ! -f "${ML_DIR}/match_scorer.joblib" ]; then
        info "  تدريب نموذج GradientBoosting (5,000 عينة تجريبية)..."
        python3 -c "
import sys
sys.path.insert(0, '.')
from core.matchmaking.ml_scorer import MLScoreEngine
engine = MLScoreEngine()
report = engine.train(n_synthetic=5000)
print(f'Train accuracy: {report.test_accuracy:.1%} | AUC: {report.test_auc:.3f}')
" 2>&1 | tail -3
        if [ $? -eq 0 ]; then
            info "  النموذج المدرب ومحفوظ ✓"
        else
            warn "  تدريب النموذج فشل (يُدرَّب أول مرة عند الاستخدام)"
        fi
    else
        info "  النموذج المدرب مسبقاً — تخطي التدريب"
    fi
else
    info "  scikit-learn غير مثبّ — تخطي تدريب النموذج (اختياري)"
fi

# ═══════════════════════════════════════════════════════════
# النتيجة
# ═══════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  التثبيت مكتمل بنجاح!                                       ${NC}"
echo -e "${GREEN}${BOLD}                                                             ${NC}"
echo -e "${GREEN}${BOLD}  التشغيل: cd $PROJECT_DIR && streamlit run app.py             ${NC}"
echo ""
echo -e "  ملاحظات:"
echo -e "     • عدّل GLM_API_KEY في .env لتفعيل الاستشارات الذكية"
echo -e "    • عدّل JWT_SECRET في .env للإنتاج (القيمة الحالية للتطوير فقط)"
echo -e "    • CRTL+C لإيقاف Streamlit"
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""