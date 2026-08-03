"""Acceptance tests for admin hydration management API."""
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-acceptance-tests")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-123")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import get_db
from app.models.base import Base

# In-memory SQLite
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_headers():
    return {"X-Admin-Key": "test-admin-key-123"}


class TestHydrateEndpoint:
    """POST /admin/hydrate"""

    def test_requires_admin_key(self, client):
        """Hydrate endpoint requires admin key header."""
        response = client.post("/api/v1/admin/hydrate", json={"age": 10})
        assert response.status_code == 401

    def test_wrong_admin_key_rejected(self, client):
        """Wrong admin key returns 401."""
        response = client.post(
            "/api/v1/admin/hydrate",
            json={"age": 10},
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_valid_admin_key_returns_202(self, client, admin_headers):
        """Valid admin key returns 202 with task_id."""
        response = client.post(
            "/api/v1/admin/hydrate",
            json={"age": 10},
            headers=admin_headers,
        )
        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["status"] in ("processing", "completed")
        assert "message" in data

    def test_invalid_age_rejected(self, client, admin_headers):
        """Age outside 6-18 returns validation error."""
        response = client.post(
            "/api/v1/admin/hydrate",
            json={"age": 25},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_invalid_limit_rejected(self, client, admin_headers):
        """Limit > 500 returns validation error."""
        response = client.post(
            "/api/v1/admin/hydrate",
            json={"age": 10, "limit": 999},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestHydrateStatusEndpoint:
    """GET /admin/hydrate/{task_id}/status"""

    def test_requires_admin_key(self, client):
        """Status endpoint requires admin key."""
        response = client.get("/api/v1/admin/hydrate/some-id/status")
        assert response.status_code == 401

    def test_invalid_uuid_returns_400(self, client, admin_headers):
        """Invalid UUID format returns 400."""
        response = client.get(
            "/api/v1/admin/hydrate/not-a-uuid/status",
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_nonexistent_task_returns_404(self, client, admin_headers):
        """Valid UUID for nonexistent task returns 404."""
        import uuid
        fake_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/admin/hydrate/{fake_id}/status",
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_task_status_after_hydrate(self, client, admin_headers):
        """After triggering hydration, task status is retrievable."""
        import uuid as uuid_mod

        # Trigger hydration
        hydrate_resp = client.post(
            "/api/v1/admin/hydrate",
            json={"age": 12},
            headers=admin_headers,
        )
        task_id = hydrate_resp.json()["task_id"]

        # Check status
        status_resp = client.get(
            f"/api/v1/admin/hydrate/{task_id}/status",
            headers=admin_headers,
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("processing", "completed", "failed")
        assert isinstance(data["books_processed"], int)
        assert isinstance(data["errors"], list)
