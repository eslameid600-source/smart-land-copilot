# Smart Land Copilot — CI/CD Pipeline Documentation

## Overview

This GitHub Actions workflow (`ci-cd.yml`) provides a complete CI/CD pipeline for the Smart Land Copilot project. It runs automatically on every push or pull request to the `main` branch.

## Pipeline Jobs

The pipeline consists of **4 independent jobs** that run in parallel (except `build` which depends on the others):

### 1. `test` — Run Tests
- **Purpose:** Execute all unit and integration tests
- **What it does:**
  - Installs Python dependencies from `requirements.txt` and `requirements-dev.txt`
  - Runs `pytest tests/` with verbose output
  - Excludes `e2e/`, `simulation/`, and `load_tests/` directories
  - Sets `MOCK_MODE=true` and `SLOWAPI_ENABLED=false` for test safety

### 2. `security` — Security Scan
- **Purpose:** Detect security vulnerabilities
- **What it does:**
  - **Bandit:** Scans all Python files for security issues (excludes `tests/`, `venv/`, `web/`, `microservices/`)
  - **Safety:** Checks installed packages for known vulnerabilities
  - Both scans are non-blocking (warnings won't fail the build)

### 3. `lint` — Code Quality
- **Purpose:** Ensure consistent code style
- **What it does:**
  - Runs `ruff check .` to lint all Python files
  - Excludes `tests/`, `web/`, `microservices/`, and `venv/`
  - Non-blocking — shows warnings but doesn't fail the build

### 4. `build` — Docker Build
- **Purpose:** Verify Docker image builds successfully
- **What it does:**
  - Builds the Docker image using `Dockerfile` with `target: test`
  - Uses Docker BuildKit caching for faster builds
  - Only runs on push to `main` (not on pull requests)
  - Depends on `test`, `security`, and `lint` jobs completing successfully

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHON_VERSION` | `3.11` | Python version used in all jobs |
| `MOCK_MODE` | `true` | Enables mock mode for tests (no external APIs) |

## Adding a New Job

To add a new job to the pipeline:

1. Add a new job block in `ci-cd.yml` following the existing pattern
2. Use `runs-on: ubuntu-latest` and `actions/checkout@v4`
3. Set up Python with `actions/setup-python@v5`
4. Install dependencies with `pip install -r requirements.txt`

Example:
```yaml
my-job:
  name: My Custom Job
  runs-on: ubuntu-latest
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
- Ensure all test dependencies are in `requirements-dev.txt`
- Verify no external API calls are made in tests

### Security scan fails
- Run `bandit -r .` locally to see exact issues
- Add security exceptions using `# nosec` comments where appropriate
- Update packages with `safety check --fix`

### Docker build fails
- Run `docker build --target test .` locally to reproduce
- Check that `Dockerfile` has all required stages
- Ensure `requirements.txt` includes all production dependencies

## Badge

```markdown
[![CI/CD](https://github.com/eslameid600-source/smart-land-copilot/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/eslameid600-source/smart-land-copilot/actions/workflows/ci-cd.yml)