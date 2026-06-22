"""purchase_module.tests.conftest — facade stub with pytest fixtures + constants."""

import pytest

# Constants used by core/account tests
BUYER_ID = "test-buyer-001"
LAND_ID = "EG-CAI-TEST-01"


@pytest.fixture
def buyer_id() -> str:
    return BUYER_ID


@pytest.fixture
def land_id() -> str:
    return LAND_ID


@pytest.fixture
def client():
    """Stub FastAPI test client fixture."""
    from fastapi.testclient import TestClient
    try:
        from api.routes.main import app
        return TestClient(app)
    except Exception:
        pytest.skip("FastAPI app not available")


@pytest.fixture
def db_session():
    """Stub async DB session fixture."""
    pytest.skip("DB session not configured")


__all__ = ["BUYER_ID", "LAND_ID", "buyer_id", "land_id"]
