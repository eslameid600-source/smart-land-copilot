.PHONY: start stop test migrate lint security clean build help

# ──────────────────────────────────────────────
# Smart Land Copilot — Makefile
# ──────────────────────────────────────────────
# or: make <command>
# ==============================================

# ─── Variables ───
DOCKER_COMPOSE = docker compose
PYTHON = python
PYTEST = pytest
BANDIT = bandit
UVICORN = uvicorn

help: ## عرض هذا المساعد
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ══════════════════════════════════════════════
# Docker
# ══════════════════════════════════════════════

start: ## تشغيل جميع الخدمات عبر Docker Compose
	$(DOCKER_COMPOSE) up -d --build
	@echo "✅ النظام يعمل على:"
	@echo "   API:      http://localhost:8000"
	@echo "   Docs:     http://localhost:8000/docs"
	@echo "   Streamlit: http://localhost:8501"
	@echo "   Postgres:  localhost:5432"
	@echo "   Redis:     localhost:6379"

stop: ## إيقاف جميع الخدمات
	$(DOCKER_COMPOSE) down
	@echo "✅ تم إيقاف جميع الخدمات"

restart: stop start ## إعادة تشغيل الخدمات

logs: ## عرض logs الخدمات
	$(DOCKER_COMPOSE) logs -f

ps: ## عرض حالة الخدمات
	$(DOCKER_COMPOSE) ps

build: ## بناء الصور دون تشغيل
	$(DOCKER_COMPOSE) build

clean: ## حذف الحاويات والـ volumes
	$(DOCKER_COMPOSE) down -v --remove-orphans
	@echo "✅ تم التنظيف"

# ══════════════════════════════════════════════
# Database
# ══════════════════════════════════════════════

migrate: ## تشغيل ترحيل قاعدة البيانات
	$(PYTHON) -m alembic upgrade head
	@echo "✅ تم تحديث قاعدة البيانات"

migrate-create: ## إنشاء ملف ترحيل جديد
	$(PYTHON) -m alembic revision --autogenerate -m "$(message)"

migrate-optimize: ## تطبيق تحسينات قاعدة البيانات (Indexes + Materialized Views)
	$(PYTHON) -m infrastructure.database.optimizations
	@echo "✅ تم تطبيق تحسينات قاعدة البيانات"

# ══════════════════════════════════════════════
# Testing
# ══════════════════════════════════════════════

test: ## تشغيل جميع الاختبارات
	$(PYTEST) tests/ -v --tb=short --ignore=tests/e2e --ignore=tests/simulation
	@echo "✅ تم تشغيل الاختبارات"

test-unit: ## تشغيل اختبارات الوحدة فقط
	$(PYTEST) tests/test_broker_delegation.py tests/test_notifications.py -v --tb=short --ignore=tests/e2e
	@echo "✅ اختبارات الوحدة اكتملت"

test-integration: ## تشغيل اختبارات التكامل
	$(PYTEST) tests/test_transfer_integration.py -v --tb=short
	@echo "✅ اختبارات التكامل اكتملت"

test-e2e: ## تشغيل اختبارات E2E (تتطلب Playwright)
	$(PYTEST) tests/e2e/ -v --tb=short --headed
	@echo "✅ اختبارات E2E اكتملت"

test-load: ## تشغيل اختبارات التحميل (تتطلب Locust)
	locust -f tests/load_tests/locustfile_full.py --host=http://localhost:8000 --headless -u 100 -r 10 --run-time 1m
	@echo "✅ اختبارات التحميل اكتملت"

test-simulation: ## تشغيل محاكاة البوتات
	$(PYTHON) tests/simulation/run_bots.py
	@echo "✅ محاكاة البوتات اكتملت"

test-security: ## تشغيل فحص الأمان
	$(BANDIT) -r . -f json -o bandit_report.json || true
	@echo "✅ فحص الأمان اكتمل — التقرير في bandit_report.json"

# ══════════════════════════════════════════════
# Security & Linting
# ══════════════════════════════════════════════

security: test-security ## فحص أمان سريع

lint: ## فحص جودة الكود
	$(PYTHON) -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true
	@echo "✅ فحص الكود اكتمل"

# ══════════════════════════════════════════════
# Development
# ══════════════════════════════════════════════

dev-api: ## تشغيل API محلياً (بدون Docker)
	$(UVICORN) api.routes.main:app --host 0.0.0.0 --port 8000 --reload

dev-ui: ## تشغيل Streamlit محلياً (بدون Docker)
	streamlit run config/app.py --server.port 8501 --server.enableCORS false

dev-worker: ## تشغيل Notification Worker محلياً
	$(PYTHON) config/notification_worker.py

# ══════════════════════════════════════════════
# Deployment & CI
# ══════════════════════════════════════════════

ci: lint test test-security ## تشغيل كامل خط الـ CI (محلياً)

# ══════════════════════════════════════════════
# Maintenance
# ══════════════════════════════════════════════

setup: ## تثبيت المتطلبات للتطوير المحلي
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install -r requirements-dev.txt 2>/dev/null || true
	$(PYTHON) -m playwright install chromium 2>/dev/null || true
	@echo "✅ تم تثبيت المتطلبات"

update: ## تحديث المتطلبات
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install --upgrade -r requirements.txt
	@echo "✅ تم تحديث المتطلبات"

reset-db: ## إعادة تعيين قاعدة البيانات (حذف + إنشاء)
	$(DOCKER_COMPOSE) stop postgres
	$(DOCKER_COMPOSE) rm -f postgres
	$(DOCKER_COMPOSE) up -d postgres
	@sleep 5
	$(MAKE) migrate
	@echo "✅ تم إعادة تعيين قاعدة البيانات"