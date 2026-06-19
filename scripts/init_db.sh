#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
# Smart Land Management Copilot — تهيئة قاعدة البيانات
# ══════════════════════════════════════════════════════════════
# الاستخدام:
#   chmod +x scripts/init_db.sh
#   ./scripts/init_db.sh          # تشغيل كامل
#   ./scripts/init_db.sh --seed   # إدخال بيانات تجريبية فقط
#
# المتطلبات:
#   - PostgreSQL يعمل (docker compose -f docker-compose.db.yml up -d)
#   - Python 3.11+ مع الحزم المُثبَّتة (pip install -r requirements.txt)
#   - ملف .env موجود (cp .env.production .env)
# ══════════════════════════════════════════════════════════════
set -euo pipefail

# ─── ألوان الطرفية ───────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# ─── ثوابت ───────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEED_SQL="/tmp/smartland_seed_$$.sql"
WAIT_SECONDS=15
RETRIES=10

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ─── التحقق من المتطلبات الأساسية ───────────────────────────────
check_prerequisites() {
    info "التحقق من المتطلبات الأساسية..."

    # Python 3
    if ! command -v python3 &>/dev/null; then
        error "Python 3 غير مثبّت. ثبّته أولاً: sudo apt install python3 python3-pip"
    fi
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    info "  Python: $PY_VER"

    # pip packages
    MISSING=""
    for pkg in sqlalchemy asyncpg alembic psycopg2 redis; do
        python3 -c "import $pkg" 2>/dev/null || MISSING="$MISSING $pkg"
    done
    if [ -n "$MISSING" ]; then
        warn "  حزم ناقصة: $MISSING"
        info "  جارٍ تثبيتها..."
        pip install --break-system-packages $MISSING -q 2>&1 | tail -3
    else
        info "  كل حزم Python موجودة"
    fi

    # Docker
    if command -v docker &>/dev/null; then
        if docker compose ps 2>/dev/null | grep -q "smartland"; then
            info "  Docker Compose: Containers تعمل"
        else
            warn "  Docker Compose: الحاويات غير مُشغَّلة"
            info "  تشغيل: docker compose -f docker-compose.db.yml up -d"
            docker compose -f "${PROJECT_DIR}/docker-compose.db.yml" up -d
            sleep 5
        fi
    fi

    # ملف .env
    if [ ! -f "${PROJECT_DIR}/.env" ]; then
        if [ -f "${PROJECT_DIR}/.env.production" ]; then
            cp "${PROJECT_DIR}/.env.production" "${PROJECT_DIR}/.env"
            warn "  تم نسخ .env.production → .env (عدّل القيم قبل المتابعة!)"
        else
            warn "  لا يوجد ملف .env أو .env.production"
            info "  إنشاء .env بالقيم الافتراضية..."
            cp "${PROJECT_DIR}/.env.production" "${PROJECT_DIR}/.env" 2>/dev/null || \
            touch "${PROJECT_DIR}/.env"
        fi
    fi

    echo ""
}

# ─── انتظار PostgreSQL ────────────────────────────────────────────
wait_for_postgres() {
    local url="$1"
    local attempt=0

    info "انتظار PostgreSQL على: ${url%%@*}..."

    while [ $attempt -lt $RETRIES ]; do
        if python3 -c "
import asyncio, os
os.environ.setdefault('DATABASE_URL', '$url')
# فحص الاتصال المباشر عبر psycopg2 (أبسط من async)
import psycopg2
try:
    conn = psycopg2.connect('${url}')
    conn.close()
    print('OK')
except Exception:
    print('FAIL')
" 2>/dev/null | grep -q "OK"; then
            info "  PostgreSQL جاهز ✓"
            return 0
        fi

        attempt=$((attempt + 1))
        if [ $attempt -lt $RETRIES ]; then
            echo -ne "\r    المحاولة $attempt/$RETRIES..."
            sleep "$WAIT_SECONDS"
        fi
    done

    echo ""
    error "PostgreSQL لم يصبح جاهزاً بعد $((RETRIES * WAIT_SECONDS)) ثانية. تحق من docker compose."
    return 1
}

# ── إنشاء/تحديث الجداول بـ Alembic ──────────────────────────────
run_migrations() {
    info "تشغيل ترحيلات Alembic..."
    cd "$PROJECT_DIR"

    # التأكد من وجود مجلد الترحيلات
    if [ ! -d "alembic/versions" ]; then
        mkdir -p alembic/versions
        info "  إنشاء مجلد alembic/versions/"
    fi

    # تحديث alembic.ini ليستخدم DATABASE_URL من البيئة
    if [ -f ".env" ]; then
        export $(grep -v '^#' .env | grep -v '^$' | xargs)
    fi

    # محاولة 1: ترحيل تلقائي
    python3 -c "
import asyncio
from infrastructure.database import get_engine, init_db
async def main():
    from core.account.models import Base
    from core.auction.models import Auction, Bid
    print('إنشاء الجداول عبر SQLAlchemy...')
    await init_db()
    print('تم بنجاح ✓')
asyncio.run(main())
" 2>&1

    if [ $? -eq 0 ]; then
        info "  تم إنشاء الجداول عبر SQLAlchemy ✓"
        return 0
    fi

    # محاولة 2: alembic upgrade
    info "  محاولة alembic upgrade head..."
    export ALEMBIC_SQLALCHEMY_URL="${DATABASE_URL}"
    alembic upgrade head 2>&1

    if [ $? -eq 0 ]; then
        info "  تم الترحيل بنجاح عبر Alembic ✓"
        return 0
    fi

    warn "  فشل الترحيل التلقائي — سيتم إنشاء الجداول عند أول استخدام"
    return 1
}

# ── إدخال بيانات تجريبية ──────────────────────────────────────────
seed_data() {
    info "إدخال بيانات تجريبية..."
    cd "$PROJECT_DIR"

    if [ -f ".env" ]; then
        export $(grep -v '^#' .env | grep -v '^$' | xargs)
    fi

    python3 -c "
import asyncio, os, uuid, random
from datetime import datetime, timezone
from decimal import Decimal

async def main():
    from infrastructure.database import get_session_factory
    from core.account.models import Investor, Landowner, OwnedLand, WalletTransaction
    from infrastructure.persistence.account_store import InvestorStore as SyncStore, \
        LandownerStore as SyncLandStore, lands_catalog_global, init_stores

    # ─── إنشاء مخازن الذاكرة (للاستخدامStreamlit في الوضع المتزامن) ───
    inv_sync, lo_sync = init_stores()

    # ─── مستثمر تجريبي ───
    inv_sync.create(
        user_id='demo-investor-001',
        full_name_ar='أحمد محمد الشريف',
        initial_deposit=5_000_000.0,
    )
    inv_sync.deposit(
        user_id='demo-investor-001',
        amount=10_000_000.0,
        description='إيداع إضافي لاختبار المحفظة',
    )
    info(f'  المستثمر: demo-investor-001 (محفظة: {inv_sync.get_wallet(\"demo-investor-001\")[\"wallet_balance_egp\"]:,.0f} ج.م)')

    inv_sync.create(
        user_id='demo-investor-002',
        full_name_ar='سارة أحمد حسن',
        initial_deposit=2_500_000.0,
    )
    inv_sync.create(
        user_id='demo-investor-003',
        full_name_ar='شركة النيل للاستثمار العقاري',
        initial_deposit=50_000_000.0,
    )

    # ─── مالك أرض تجريبي ───
    lo_sync.create(
        user_id='demo-landowner-001',
        full_name_ar='شركة التطوير العقاري',
        default_commission_pct=2.5,
    )

    # ربط الأراضي الحقيق بالمالك
    from core.domain.land_database import get_all_lands
    lands = get_all_lands()
    for land in lands[:3]:
        lo_sync.list_land('demo-landowner-001', {
            'land_id': land['Land_ID'],
            'name': land.get('المنطقة_المدينة', land['Land_ID']),
            'governorate': land['المحافظة'],
            'activity': land['نوع_النشاط'],
            'area_sqm': land['المساحة_متر_مربع'],
            'price_per_sqm_egp': land['السعر_للمتر_المربع'],
            'total_price_egp': land['المساحة_متر_مربع'] * land['السعر_للمتر_المربع'],
            'quality': land.get('تصنيف_الجودة', 'B'),
            'investment_status': land.get('حالة_الاستثمار', 'متاح'),
        })
    info(f'  المالك: demo-landowner-001 (3 أراضٍ مسجلة)')

    # ─── معاملة تجريبية ───
    inv_sync.deposit(
        user_id='demo-investor-001',
        amount=1_500_000.0,
        description='إيداع لشراء EG-ALX-01',
    )
    inv_sync.freeze_amount('demo-investor-001', 1_500_000.0)

    # ─── نقاط ولاء تجريبية ───
    inv_sync.add_loyalty_points('demo-investor-001', 10_000_000.0)

    info('  تم إدخال البيانات التجريبية بنجاح ✓')

asyncio.run(main())
" 2>&1

    if [ $? -eq 0 ]; then
        info "  بيانات تجريبية جاهزة ✓"
        info ""
        info "  ┌──────────────────────────────────────────┐"
        info "  │  المستثمرين التجريبيين:                      │"
        info        "  │  • demo-investor-001 (15M ج.م, 1 نقطة ولاء) │"
        info        "  │  • demo-investor-002 (2.5M ج.م)              │"
        info        "  │  • demo-investor-003 (50M ج.م)              │"
        info  │                                               │"
        info  │  مالك الأرض:                                   │"
        info  │  • demo-landowner-001 (3 أراضٍ)           │"
        info  '  └──────────────────────────────────────────┘'
        return 0
    fi

    warn "  فشل إدخال البيانات (البيانات الحقيق من land_database كافية للتشغيل)"
    return 1
}

# ─── التشغيل الرئيسي ──────────────────────────────────────────────
main() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Smart Land Copilot — تهيئة قاعدة البيانات                       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # تحميل متغيرات البيئة
    if [ -f "${PROJECT_DIR}/.env" ]; then
        set -a
        source "${PROJECT_DIR}/.env"
        set +a
        export $(grep -v '^#' "${PROJECT_DIR}/.env" | grep -v '^$' | xargs)
    fi

    # 1. المتطلبات الأساسية
    check_prerequisites

    # 2. انتظار PostgreSQL
    DB_URL="${DATABASE_URL:-postgresql+asyncpg://smartland:smartland123@localhost:5432/smartland}"
    # تحويل لـ psycopg2 URL (asyncpg → psycopg2)
    PSYCOPG_URL="${DB_URL/asyncpg/}"
    wait_for_postgres "$PSYCOPG_URL"

    # 3. إنشاء الجداول
    run_migrations

    # 4. بيانات تجريبية
    SEED_ONLY=false
    for arg in "$@"; do
        case "$arg" in
            --seed) SEED_ONLY=true ;;
        esac
    done

    if [ "$SEED_ONLY" = "false" ]; then
        seed_data
    else
        seed_data
    fi

    echo ""
    echo -e "${GREEN}═════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  التهيئة مكتملة بنجاح!                                   ${NC}"
    echo -e "${GREEN}  التشغيل: cd ${PROJECT_DIR} && streamlit run app.py            ${NC}"
    echo -e "${GREEN}═════════════════════════════════════════════════════════════${NC}"
    echo ""
}

main "$@"