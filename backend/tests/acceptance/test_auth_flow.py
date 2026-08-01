"""Acceptance tests for the authentication flow — written BEFORE implementation.

These tests define the expected behavior from a user's perspective.
They use the FastAPI TestClient to make real HTTP requests.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db
from app.models.base import Base

# In-memory SQLite for acceptance tests
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_acceptance.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
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
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


class TestUserRegistration:
    """Acceptance tests: User can create an account."""

    def test_user_can_register_with_valid_data(self, client):
        """A new user can register with email, password, and display name."""
        response = client.post("/api/v1/auth/register", json={
            "email": "alice@example.com",
            "password": "securePassword123",
            "display_name": "Alice",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "alice@example.com"
        assert data["display_name"] == "Alice"
        assert "id" in data

    def test_duplicate_email_is_rejected(self, client):
        """Registering with an existing email returns 409."""
        client.post("/api/v1/auth/register", json={
            "email": "bob@example.com", "password": "securePass123", "display_name": "Bob",
        })
        response = client.post("/api/v1/auth/register", json={
            "email": "bob@example.com", "password": "otherPass456", "display_name": "Bobby",
        })
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_weak_password_is_rejected(self, client):
        """Password must be at least 8 characters."""
        response = client.post("/api/v1/auth/register", json={
            "email": "eve@example.com", "password": "short", "display_name": "Eve",
        })
        assert response.status_code == 422  # Pydantic validation error


class TestUserLogin:
    """Acceptance tests: User can log in."""

    def test_user_can_login_with_correct_credentials(self, client):
        """A registered user can log in and receive tokens."""
        client.post("/api/v1/auth/register", json={
            "email": "alice@example.com", "password": "securePass123", "display_name": "Alice",
        })
        response = client.post("/api/v1/auth/login", json={
            "email": "alice@example.com", "password": "securePass123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_wrong_password_returns_401(self, client):
        """Incorrect password returns 401."""
        client.post("/api/v1/auth/register", json={
            "email": "alice@example.com", "password": "securePass123", "display_name": "Alice",
        })
        response = client.post("/api/v1/auth/login", json={
            "email": "alice@example.com", "password": "wrongPassword",
        })
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()


class TestTokenRefresh:
    """Acceptance tests: Token refresh works."""

    def test_valid_refresh_token_returns_new_tokens(self, client):
        """A valid refresh token can be exchanged for new access + refresh tokens."""
        client.post("/api/v1/auth/register", json={
            "email": "alice@example.com", "password": "securePass123", "display_name": "Alice",
        })
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "alice@example.com", "password": "securePass123",
        })
        refresh_token = login_resp.json()["refresh_token"]

        response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # Tokens should be different
        assert data["access_token"] != login_resp.json()["access_token"]
