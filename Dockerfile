# ──────────────────────────────────────────────
# Smart Land Copilot — Multi-stage Dockerfile
# ──────────────────────────────────────────────

# ==============================================
# Stage 1: Base (Python 3.11 slim)
# ==============================================
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ==============================================
# Stage 2: Production (FastAPI Backend)
# ==============================================
FROM base AS production

# Copy only requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/notifications/health || exit 1

CMD ["uvicorn", "api.routes.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ==============================================
# Stage 3: Streamlit Frontend
# ==============================================
FROM base AS streamlit

# Copy only requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "config/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.enableCORS=false"]

# ==============================================
# Stage 4: Development (with hot reload)
# ==============================================
FROM base AS development

COPY requirements.txt requirements-dev.txt* ./
RUN pip install --no-cache-dir -r requirements.txt && \
    (test -f requirements-dev.txt && pip install --no-cache-dir -r requirements-dev.txt || true)

COPY . .

EXPOSE 8000 8501

CMD ["uvicorn", "api.routes.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ==============================================
# Stage 5: Test (includes all test dependencies)
# ==============================================
FROM base AS test

COPY requirements.txt requirements-dev.txt* ./
RUN pip install --no-cache-dir -r requirements.txt && \
    (test -f requirements-dev.txt && pip install --no-cache-dir -r requirements-dev.txt || true) && \
    pip install bandit pytest pytest-asyncio

COPY . .

# Run linting and security checks
RUN python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true

# Run tests (ignore E2E and simulation which need browsers/services)
CMD ["pytest", "tests/", "-v", "--tb=short", "--ignore=tests/e2e", "--ignore=tests/simulation", "-x"]