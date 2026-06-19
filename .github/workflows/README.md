# Smart Land Copilot — CI/CD Pipeline Documentation

## Overview

This GitHub Actions workflow (`ci-cd.yml`) provides a complete CI/CD pipeline for the Smart Land Copilot project. It runs automatically on every push or pull request to the `main` branch.

## Pipeline Jobs

The pipeline consists of **6 jobs** — 5 run in parallel, and `build` depends on them:

### 1. `syntax-check` — Python Syntax Check
- **Purpose:** Verify all Python files have valid syntax
- **What it does:**
  - Uses `python -m py_compile` on all `.py` files
  - Excludes `venv/`, `.venv/`, `__pycache__/`
  - Non-blocking — completes quickly

### 2. `lint` — Code Quality (Flake8 + Ruff + mypy + black + isort)
- **Purpose:** Enforce code style and catch potential issues
- **What it does:**
  - **Flake8:** Checks for critical syntax errors (E9, F63, F7, F82)
  - **Ruff:** Fast Python linter
  - **mypy:** Static type checking for `api/` and `core/`
  - **black:** Code formatting check
  - **isort:** Import sorting check
  - All checks are non-blocking (`|| true`)
- **Caching:** Uses `actions/cache@v4` for pip dependencies

### 3. `security` — Security Scan
- **Purpose:** Detect security vulnerabilities and exposed secrets
- **What it does:**
  - **Bandit:** Scans Python files for security issues (excludes `tests/`, `venv/`, `web/`, `microservices/`)
  - **Safety:** Checks installed packages for known vulnerabilities
  - **TruffleHog:** Scans for leaked secrets/API keys in git history
  - All scans are non-blocking
  - Reports uploaded as artifacts (`security-reports`)
- **Caching:** Uses `actions/cache@v4` for pip dependencies

### 4. `test` — Run Tests with Coverage
- **Purpose:** Execute unit/integration tests and measure coverage
- **What it does:**
  - Installs dependencies from `requirements.txt` + `requirements-dev.txt`
  - Runs `pytest tests/` with verbose output
  - Excludes `e2e/`, `simulation/`, `load_tests/`
  - Requires **80% minimum coverage** (`--cov-fail-under=80`)
  - Uses in-memory SQLite (`sqlite+aiosqlite:///:memory:`)
  - Requires **Redis service** (redis:7-alpine) for cache-dependent tests
- **Caching:** Uses `actions/cache@v4` for pip dependencies
- **Artifacts:** Uploads `coverage.xml`

### 5. `build` — Build & Push Docker Image
- **Purpose:** Verify and publish Docker image
- **What it does:**
  - Builds using `Dockerfile` with `target: test`
  - **Pushes to Docker Hub** on push to `main`
  - Tags: `land-copilot:<sha>` and `land-copilot:latest`
  - Uses Docker BuildKit caching (`type=gha`)
- **Depends on:** `syntax-check`, `lint`, `security`, `test`
- **Only runs on:** Push to `main` (not pull requests)

### 6. `notify` — Notify on Failure
- **Purpose:** Alert team when pipeline fails
- **What it does:**
  - Sends **Slack message** to `#ci-cd-notifications` channel
  - Triggered only when any previous job fails (`if: failure()`)
  - Includes commit SHA, author, and run URL
- **Depends on:** All other jobs

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHON_VERSION` | `3.11` | Python version used in all jobs |
| `MOCK_MODE` | `true` | Enables mock mode for tests |
| `DATABASE_URL` | `sqlite+aiosqlite:///:memory:` | In-memory SQLite for fast tests |
| `REDIS_HOST` | `localhost` | Redis host for CI |
| `REDIS_PORT` | `6379` | Redis port |
| `JWT_SECRET` | `test-jwt-secret` | Fake JWT for tests |
| `AI_PROVIDER` | `mock` | No external AI calls in CI |
| `ERP_ENABLED` | `false` | Skip ERP integration in tests |

## Required Secrets

To enable full functionality, configure these secrets in GitHub Settings:

| Secret | Description | Used In |
|--------|-------------|---------|
| `DOCKERHUB_USERNAME` | Docker Hub username | `build` job |
| `DOCKERHUB_TOKEN` | Docker Hub access token | `build` job |
| `SLACK_BOT_TOKEN` | Slack bot token for notifications | `notify` job |

## Adding a New Job

To add a new job to the pipeline:

1. Add a new job block in `ci-cd.yml` following the existing pattern
2. Use `runs-on: ubuntu-latest` and `actions/checkout@v4`
3. Set up Python with `actions/setup-python@v5`
4. Install dependencies with `pip install -r requirements.txt`
5. Add caching with `actions/cache@v4` for faster builds

Example:
```yaml
my-job:
  name: My Custom Job
  runs-on: ubuntu-latest
  timeout-minutes: 10
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: ${{ env.PYTHON_VERSION }}
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    - name: Run my task
      run: |
        my-command
```

## Troubleshooting

### Tests fail in CI but pass locally
- Check that `MOCK_MODE=true` is set
- Ensure `DATABASE_URL=sqlite+aiosqlite:///:memory:` is used
- Verify Redis service is healthy
- Check all test dependencies are in `requirements-dev.txt`

### Security scan fails
- Run `bandit -r .` locally to see exact issues
- Add `# nosec` comments where appropriate for false positives
- Update packages with `safety check --fix`

### Docker build fails
- Run `docker build --target test .` locally to reproduce
- Check that `Dockerfile` has all required stages
- Ensure `requirements.txt` includes all production dependencies

### TruffleHog reports secrets
- Review `trufflehog_report.json` artifact
- If false positives (test data), consider excluding those files
- If real secrets, rotate immediately and remove from history

## CI/CD Badge

Add this to your README.md:

```markdown
[![CI/CD](https://github.com/eslameid600-source/smart-land-copilot/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/eslameid600-source/smart-land-copilot/actions/workflows/ci-cd.yml)
```

## Performance

| Job | Typical Duration | Caching |
|-----|------------------|---------|
| syntax-check | ~30s | No |
| lint | ~1-2min | Yes (pip) |
| security | ~1-2min | Yes (pip) |
| test | ~3-5min | Yes (pip) |
| build | ~5-10min | Yes (Docker GHA) |
| notify | <10s | No |

**Total CI time:** ~5-10 minutes for full pipeline