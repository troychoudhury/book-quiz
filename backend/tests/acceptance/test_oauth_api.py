"""Acceptance tests for the SSO OAuth flow (Google, Facebook, Microsoft).

These tests exercise the real HTTP endpoints with a TestClient, an in-memory
SQLite database, a fake Redis, and a mocked provider token exchange (the
provider HTTP calls are external and must never run in tests).
"""
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-acceptance-tests")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.config import get_settings
from app.core.database import get_db
from app.models.base import Base
from app.models.user import User
from app.models.user_oauth_link import UserOAuthLink
from app.services.auth_service import AuthService
from app.services.oauth_service import OAuthService

settings = get_settings()

# In-memory SQLite for acceptance tests (same pattern as other test modules).
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

from app.api import oauth as oauth_api  # noqa: E402  (needs app.dependency_overrides first)


class FakeRedis:
    """Minimal dict-backed stand-in for the Redis client."""

    def __init__(self):
        self.data: dict = {}

    def set(self, key, value, ex=None):
        self.data[key] = value
        return True

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        return self.data.pop(key, None) is not None


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def oauth_environment(monkeypatch):
    """Configure providers, inject the fake Redis, and reset it per test."""
    for provider in OAuthService.PROVIDERS:
        monkeypatch.setattr(settings, f"{provider}_client_id", f"test-{provider}-id")
        monkeypatch.setattr(settings, f"{provider}_client_secret", f"test-{provider}-secret")
    oauth_api.oauth._redis = FakeRedis()
    yield
    for provider in OAuthService.PROVIDERS:
        monkeypatch.setattr(settings, f"{provider}_client_id", "")
        monkeypatch.setattr(settings, f"{provider}_client_secret", "")


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def google_userinfo():
    """Normalized userinfo dict returned by the (mocked) provider exchange."""
    return {
        "provider": "google",
        "provider_user_id": "google-sub-123",
        "email": "sso@example.com",
        "name": "SSO User",
        "avatar_url": "https://example.com/avatar.png",
    }


def _start_oauth(client, provider="google", **params):
    """Hit the login endpoint and return (response, state)."""
    response = client.get(f"/api/v1/auth/oauth/{provider}/login", params=params or None)
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]
    return response, location, state


class TestProvidersEndpoint:
    def test_lists_configured_providers(self, client):
        response = client.get("/api/v1/auth/oauth/providers")
        assert response.status_code == 200
        providers = response.json()["providers"]
        names = {p["provider"]: p["name"] for p in providers}
        assert names == {"google": "Google", "facebook": "Facebook", "microsoft": "Microsoft"}

    def test_provider_hidden_when_not_configured(self, client, monkeypatch):
        monkeypatch.setattr(settings, "microsoft_client_id", "")
        response = client.get("/api/v1/auth/oauth/providers")
        assert "microsoft" not in {p["provider"] for p in response.json()["providers"]}


class TestOAuthLogin:
    def test_redirects_to_provider_with_state(self, client):
        response, location, state = _start_oauth(client)
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
        assert "code_challenge=" in location  # PKCE
        assert state

    def test_unknown_provider_returns_404(self, client):
        response = client.get("/api/v1/auth/oauth/apple/login")
        assert response.status_code == 404

    def test_link_account_requires_auth(self, client):
        response = client.get("/api/v1/auth/oauth/google/login", params={"link_account": "true"})
        assert response.status_code == 401

    def test_link_account_embeds_user_in_state(self, client):
        db = TestingSessionLocal()
        auth = AuthService(db)
        user = auth.register("linker@example.com", "SecurePass123!", "Linker")
        token = auth.create_access_token(user.id)
        db.close()

        response = client.get(
            "/api/v1/auth/oauth/google/login",
            params={"link_account": "true"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 302
        state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
        payload = oauth_api.oauth.consume_state(state)
        assert payload["link_user_id"] == str(user.id)

    def test_redis_down_returns_503(self, client, monkeypatch):
        import redis as redis_lib

        class BrokenRedis(FakeRedis):
            def set(self, key, value, ex=None):
                raise redis_lib.exceptions.ConnectionError("down")

        oauth_api.oauth._redis = BrokenRedis()
        response = client.get("/api/v1/auth/oauth/google/login")
        assert response.status_code == 503


class TestOAuthCallback:
    def test_full_login_flow_creates_user_and_issues_jwt(self, client, monkeypatch, google_userinfo):
        """First-time SSO signup: user created, tokens delivered via fragment."""
        _, _, state = _start_oauth(client)
        monkeypatch.setattr(oauth_api.oauth, "exchange_code", lambda *a, **kw: google_userinfo)

        response = client.get(
            "/api/v1/auth/oauth/google/callback", params={"code": "auth-code", "state": state}
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("http://localhost:5173/auth/callback#")
        fragment = dict(parse_qs(location.split("#", 1)[1]))
        assert fragment["access_token"][0]
        assert fragment["refresh_token"][0]

        db = TestingSessionLocal()
        user = db.query(User).filter(User.email == "sso@example.com").first()
        assert user is not None
        assert user.password_hash is None  # SSO-only account
        assert user.display_name == "SSO User"
        assert user.avatar_url == "https://example.com/avatar.png"
        link = db.query(UserOAuthLink).filter(UserOAuthLink.user_id == user.id).first()
        assert link.provider == "google"
        assert link.provider_user_id == "google-sub-123"
        db.close()

    def test_state_deleted_after_callback(self, client, monkeypatch, google_userinfo):
        """B3: the Redis state key must be consumed (single use)."""
        _, _, state = _start_oauth(client)
        monkeypatch.setattr(oauth_api.oauth, "exchange_code", lambda *a, **kw: google_userinfo)
        client.get("/api/v1/auth/oauth/google/callback", params={"code": "c", "state": state})
        assert oauth_api.oauth.consume_state(state) is None

    def test_replay_of_consumed_state_rejected(self, client, monkeypatch, google_userinfo):
        """Reusing a consumed state must fail with 400 (CSRF protection)."""
        _, _, state = _start_oauth(client)
        monkeypatch.setattr(oauth_api.oauth, "exchange_code", lambda *a, **kw: google_userinfo)
        first = client.get("/api/v1/auth/oauth/google/callback", params={"code": "c", "state": state})
        assert first.status_code == 302
        replay = client.get("/api/v1/auth/oauth/google/callback", params={"code": "c", "state": state})
        assert replay.status_code == 400

    def test_state_mismatch_returns_400(self, client):
        response = client.get(
            "/api/v1/auth/oauth/google/callback", params={"code": "c", "state": "bogus"}
        )
        assert response.status_code == 400
        assert "CSRF" in response.json()["detail"]

    def test_provider_denial_redirects_to_frontend_login(self, client):
        response = client.get(
            "/api/v1/auth/oauth/google/callback", params={"error": "access_denied"}
        )
        assert response.status_code == 302
        assert "login?error=access_denied" in response.headers["location"]

    def test_auto_link_by_email(self, client, monkeypatch, google_userinfo):
        """Existing email/password user with same email gets the provider linked."""
        db = TestingSessionLocal()
        auth = AuthService(db)
        user = auth.register("sso@example.com", "SecurePass123!", "Existing User")
        db.close()

        _, _, state = _start_oauth(client)
        monkeypatch.setattr(oauth_api.oauth, "exchange_code", lambda *a, **kw: google_userinfo)
        response = client.get(
            "/api/v1/auth/oauth/google/callback", params={"code": "c", "state": state}
        )
        assert response.status_code == 302

        db = TestingSessionLocal()
        link = db.query(UserOAuthLink).filter(UserOAuthLink.user_id == user.id).first()
        assert link is not None and link.provider == "google"
        # Password account is unchanged.
        still = db.get(User, user.id)
        assert still.password_hash is not None
        db.close()

    def test_link_account_flow_no_tokens(self, client, monkeypatch, google_userinfo):
        """Link-account flow binds the provider and redirects to the profile."""
        db = TestingSessionLocal()
        auth = AuthService(db)
        user = auth.register("linker@example.com", "SecurePass123!", "Linker")
        token = auth.create_access_token(user.id)
        db.close()

        response = client.get(
            "/api/v1/auth/oauth/google/login",
            params={"link_account": "true", "redirect_to": "/profile"},
            headers={"Authorization": f"Bearer {token}"},
        )
        state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
        monkeypatch.setattr(oauth_api.oauth, "exchange_code", lambda *a, **kw: google_userinfo)

        response = client.get(
            "/api/v1/auth/oauth/google/callback", params={"code": "c", "state": state}
        )
        assert response.status_code == 302
        assert response.headers["location"] == "http://localhost:5173/profile"

        db = TestingSessionLocal()
        link = db.query(UserOAuthLink).filter(UserOAuthLink.user_id == user.id).first()
        assert link is not None and link.provider == "google"
        db.close()

    def test_sso_user_cannot_password_login(self, client, monkeypatch, google_userinfo):
        """Q4: SSO-only accounts must not authenticate with a password."""
        db = TestingSessionLocal()
        auth = AuthService(db)
        auth.create_user_from_oauth("sso@example.com", "SSO User", None)
        db.close()

        response = client.post(
            "/api/v1/auth/login", json={"email": "sso@example.com", "password": "whatever123"}
        )
        assert response.status_code == 401


class TestOAuthLinks:
    def _register_and_token(self, email="links@example.com", password="SecurePass123!"):
        db = TestingSessionLocal()
        auth = AuthService(db)
        user = auth.register(email, password, "Linker")
        token = auth.create_access_token(user.id)
        db.close()
        return token, user.id

    def test_list_links_empty(self, client):
        token, _ = self._register_and_token()
        response = client.get(
            "/api/v1/users/me/oauth-links", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_list_and_unlink(self, client):
        token, user_id = self._register_and_token()
        db = TestingSessionLocal()
        auth = AuthService(db)
        auth.link_oauth_provider(user_id, "google", "g1", "links@example.com", "Linker", None)
        auth.link_oauth_provider(user_id, "microsoft", "m1", "links@example.com", "Linker", None)
        db.close()

        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/v1/users/me/oauth-links", headers=headers)
        assert response.status_code == 200
        providers = {item["provider"] for item in response.json()}
        assert providers == {"google", "microsoft"}
        assert all(item["linked_at"] for item in response.json())

        response = client.delete("/api/v1/users/me/oauth-links/microsoft", headers=headers)
        assert response.status_code == 204
        remaining = client.get("/api/v1/users/me/oauth-links", headers=headers).json()
        assert {item["provider"] for item in remaining} == {"google"}

    def test_unlink_not_linked_returns_404(self, client):
        token, _ = self._register_and_token()
        response = client.delete(
            "/api/v1/users/me/oauth-links/google", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404

    def test_cannot_unlink_last_method_without_password(self, client):
        """Q7: SSO-only user cannot unlink their only provider."""
        db = TestingSessionLocal()
        auth = AuthService(db)
        user = auth.create_user_from_oauth("only@example.com", "Only SSO", None)
        auth.link_oauth_provider(user.id, "google", "g1", "only@example.com", "Only SSO", None)
        token = auth.create_access_token(user.id)
        db.close()

        response = client.delete(
            "/api/v1/users/me/oauth-links/google", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 400
        assert "last authentication method" in response.json()["detail"]

    def test_can_unlink_when_another_method_exists(self, client):
        db = TestingSessionLocal()
        auth = AuthService(db)
        user = auth.create_user_from_oauth("multi@example.com", "Multi", None)
        auth.link_oauth_provider(user.id, "google", "g1", "multi@example.com", "Multi", None)
        auth.link_oauth_provider(user.id, "facebook", "f1", "multi@example.com", "Multi", None)
        token = auth.create_access_token(user.id)
        db.close()

        response = client.delete(
            "/api/v1/users/me/oauth-links/google", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 204


class TestProfileFields:
    def test_profile_includes_avatar_and_has_password(self, client):
        db = TestingSessionLocal()
        auth = AuthService(db)
        user = auth.create_user_from_oauth("avatar@example.com", "Avatar", "https://img/a.png")
        token = auth.create_access_token(user.id)
        db.close()

        response = client.get(
            "/api/v1/users/me/profile", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["avatar_url"] == "https://img/a.png"
        assert data["has_password"] is False

    def test_profile_has_password_true_for_password_account(self, client):
        db = TestingSessionLocal()
        auth = AuthService(db)
        user = auth.register("pw@example.com", "SecurePass123!", "PW User")
        token = auth.create_access_token(user.id)
        db.close()

        data = client.get(
            "/api/v1/users/me/profile", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert data["has_password"] is True
        assert data["avatar_url"] is None


class TestAuthServiceOAuthMethods:
    def test_link_oauth_provider_idempotent(self):
        """R1: linking twice must not create a duplicate row."""
        db = TestingSessionLocal()
        auth = AuthService(db)
        user = auth.create_user_from_oauth("dup@example.com", "Dup", None)
        first = auth.link_oauth_provider(user.id, "google", "g1", "dup@example.com", "Dup", None)
        second = auth.link_oauth_provider(user.id, "google", "g1", "dup@example.com", "Dup", None)
        assert first is True
        assert second is False
        count = (
            db.query(UserOAuthLink)
            .filter(UserOAuthLink.user_id == user.id, UserOAuthLink.provider == "google")
            .count()
        )
        assert count == 1
        db.close()
