"""Acceptance tests for admin hydration management API."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-acceptance-tests")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-123")

import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import get_db
from app.models.base import Base
from app.services.hydration_service import HydrationService

import app.api.admin as admin_module

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


@pytest.fixture(autouse=True)
def hydrate_all_test_environment(monkeypatch):
    """Isolate background hydrate-all tasks between tests.

    Clears the in-memory task store and points the background worker's
    session factory at the SQLite test engine (the request-scoped
    ``get_db`` override does not apply to worker threads).
    """
    admin_module._tasks.clear()
    monkeypatch.setattr(admin_module, "SessionLocal", TestingSessionLocal)
    yield
    admin_module._tasks.clear()


@pytest.fixture
def client():
    """TestClient with a long-lived portal (context manager).

    Must be used as a context manager so background ``asyncio.create_task``
    work survives between requests, matching how uvicorn runs the app.
    Without it, starlette creates a per-request portal whose loop shutdown
    blocks on (and cancels) background tasks.
    """
    with TestClient(app) as test_client:
        yield test_client


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
        fake_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/admin/hydrate/{fake_id}/status",
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_task_status_after_hydrate(self, client, admin_headers):
        """After triggering hydration, task status is retrievable."""
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


def _fake_fetch_books(self, age, limit=100):
    """Stand-in for HydrationService.fetch_top_books_for_age.

    Returns 3 books per call so per-grade counts are predictable without
    hitting the OpenLibrary API.
    """
    return [
        {
            "id": str(uuid.uuid4()),
            "title": f"Book age={age} n={i}",
            "author": "Fake Author",
            "isbn": f"97800000{age:02d}{i:03d}",
        }
        for i in range(3)
    ]


def _wait_for_task(client, admin_headers, task_id, timeout=10.0):
    """Poll the hydrate-all status endpoint until the task finishes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(
            f"/api/v1/admin/hydrate-all/{task_id}/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.05)
    raise AssertionError(f"Task {task_id} did not finish within {timeout}s")


class TestHydrateAllEndpoint:
    """POST /admin/hydrate-all"""

    def test_requires_admin_key(self, client):
        """Hydrate-all endpoint requires admin key header."""
        response = client.post(
            "/api/v1/admin/hydrate-all",
            json={"start_grade": 1, "end_grade": 12},
        )
        assert response.status_code == 401

    def test_wrong_admin_key_rejected(self, client):
        """Wrong admin key returns 401."""
        response = client.post(
            "/api/v1/admin/hydrate-all",
            json={"start_grade": 1, "end_grade": 12},
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_valid_request_returns_202(self, client, admin_headers, monkeypatch):
        """Valid request returns 202 immediately with a task_id."""
        monkeypatch.setattr(
            HydrationService, "fetch_top_books_for_age", _fake_fetch_books
        )
        response = client.post(
            "/api/v1/admin/hydrate-all",
            json={"start_grade": 1, "end_grade": 12, "books_per_grade": 100},
            headers=admin_headers,
        )
        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "processing"
        assert "message" in data

        # Wait for the background task so it cannot leak into other tests.
        task_data = _wait_for_task(client, admin_headers, data["task_id"])
        assert task_data["status"] == "completed"

    def test_defaults_to_full_grade_range(self, client, admin_headers, monkeypatch):
        """Omitted fields default to grades 1-12 and 100 books per grade."""
        monkeypatch.setattr(
            HydrationService, "fetch_top_books_for_age", _fake_fetch_books
        )
        response = client.post(
            "/api/v1/admin/hydrate-all",
            json={},
            headers=admin_headers,
        )
        assert response.status_code == 202
        task_data = _wait_for_task(client, admin_headers, response.json()["task_id"])
        assert task_data["start_grade"] == 1
        assert task_data["end_grade"] == 12
        assert task_data["books_per_grade"] == 100
        assert len(task_data["grades"]) == 12

    def test_invalid_grade_bounds_rejected(self, client, admin_headers):
        """Grades outside 1-12 and out-of-range limits return 422."""
        invalid_payloads = [
            {"start_grade": 0},
            {"end_grade": 13},
            {"books_per_grade": 0},
            {"books_per_grade": 501},
        ]
        for payload in invalid_payloads:
            response = client.post(
                "/api/v1/admin/hydrate-all",
                json=payload,
                headers=admin_headers,
            )
            assert response.status_code == 422, f"payload {payload} not rejected"

    def test_inverted_grade_range_rejected(self, client, admin_headers):
        """start_grade > end_grade returns 422."""
        response = client.post(
            "/api/v1/admin/hydrate-all",
            json={"start_grade": 7, "end_grade": 3},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_concurrent_hydrate_rejected_with_409(
        self, client, admin_headers, monkeypatch
    ):
        """A second hydrate-all call while one is processing returns 409."""
        release = threading.Event()

        def blocking_fetch(self, age, limit=100):
            release.wait(timeout=10)
            return [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Blocked Book",
                    "author": "Fake Author",
                    "isbn": f"978000000000{age:02d}",
                }
            ]

        monkeypatch.setattr(HydrationService, "fetch_top_books_for_age", blocking_fetch)
        try:
            first = client.post(
                "/api/v1/admin/hydrate-all",
                json={"start_grade": 1, "end_grade": 2},
                headers=admin_headers,
            )
            assert first.status_code == 202

            second = client.post(
                "/api/v1/admin/hydrate-all",
                json={"start_grade": 3, "end_grade": 4},
                headers=admin_headers,
            )
            assert second.status_code == 409
        finally:
            release.set()

        # Let the first task finish so it does not leak into other tests.
        task_data = _wait_for_task(client, admin_headers, first.json()["task_id"])
        assert task_data["status"] == "completed"


class TestHydrateAllStatusEndpoint:
    """GET /admin/hydrate-all/{task_id}/status"""

    def test_requires_admin_key(self, client):
        """Status endpoint requires admin key."""
        response = client.get("/api/v1/admin/hydrate-all/some-id/status")
        assert response.status_code == 401

    def test_invalid_uuid_returns_400(self, client, admin_headers):
        """Invalid UUID format returns 400."""
        response = client.get(
            "/api/v1/admin/hydrate-all/not-a-uuid/status",
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_nonexistent_task_returns_404(self, client, admin_headers):
        """Valid UUID for nonexistent task returns 404."""
        fake_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/admin/hydrate-all/{fake_id}/status",
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_status_returns_per_grade_breakdown(
        self, client, admin_headers, monkeypatch
    ):
        """Status returns per-grade breakdown plus aggregate totals."""
        monkeypatch.setattr(
            HydrationService, "fetch_top_books_for_age", _fake_fetch_books
        )
        resp = client.post(
            "/api/v1/admin/hydrate-all",
            json={"start_grade": 3, "end_grade": 5, "books_per_grade": 100},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        task_id = resp.json()["task_id"]

        data = _wait_for_task(client, admin_headers, task_id)
        assert data["task_id"] == task_id
        assert data["status"] == "completed"
        assert data["start_grade"] == 3
        assert data["end_grade"] == 5
        assert data["books_per_grade"] == 100

        # GRADE_AGE_MAP: grade 3 -> age 8, 4 -> 9, 5 -> 10
        assert [entry["grade"] for entry in data["grades"]] == [3, 4, 5]
        assert [entry["age"] for entry in data["grades"]] == [8, 9, 10]
        for entry in data["grades"]:
            assert entry["status"] == "completed"
            assert entry["books_processed"] == 3
            assert entry["error"] is None

        assert data["books_processed"] == 9
        assert data["questions_generated"] == 0
        assert data["errors"] == []
