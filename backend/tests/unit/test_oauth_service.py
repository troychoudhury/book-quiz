"""Unit tests for the OAuth service: provider userinfo parsing, state storage."""
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-acceptance-tests")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest

from app.core.config import get_settings
from app.services.oauth_service import (
    OAuthProviderError,
    OAuthRedisUnavailableError,
    OAuthService,
)

settings = get_settings()


class FakeRedis:
    """Minimal dict-backed stand-in for the Redis client used in tests."""

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
def configured_providers(monkeypatch):
    """Enable all three providers for the duration of the test."""
    for provider in OAuthService.PROVIDERS:
        monkeypatch.setattr(settings, f"{provider}_client_id", f"test-{provider}-id")
        monkeypatch.setattr(settings, f"{provider}_client_secret", f"test-{provider}-secret")
    yield
    for provider in OAuthService.PROVIDERS:
        monkeypatch.setattr(settings, f"{provider}_client_id", "")
        monkeypatch.setattr(settings, f"{provider}_client_secret", "")


@pytest.fixture
def oauth():
    service = OAuthService()
    service._redis = FakeRedis()
    return service


class TestConfiguredProviders:
    def test_all_providers_configured_when_client_ids_set(self):
        assert OAuthService.configured_providers() == ["google", "facebook", "microsoft"]

    def test_missing_client_id_hides_provider(self, monkeypatch):
        monkeypatch.setattr(settings, "facebook_client_id", "")
        assert "facebook" not in OAuthService.configured_providers()


class TestParseUserinfo:
    def test_google(self):
        info = OAuthService._parse_userinfo(
            "google",
            {"sub": "g123", "email": "a@example.com", "name": "Alice", "picture": "https://img/a.png"},
        )
        assert info == {
            "provider": "google",
            "provider_user_id": "g123",
            "email": "a@example.com",
            "name": "Alice",
            "avatar_url": "https://img/a.png",
        }

    def test_facebook_extracts_picture_url(self):
        info = OAuthService._parse_userinfo(
            "facebook",
            {
                "id": "fb456",
                "email": "b@example.com",
                "name": "Bob",
                "picture": {"data": {"url": "https://img/b.png"}},
            },
        )
        assert info["provider_user_id"] == "fb456"
        assert info["avatar_url"] == "https://img/b.png"

    def test_microsoft_uses_mail_then_upn(self):
        info = OAuthService._parse_userinfo(
            "microsoft",
            {"id": "ms789", "displayName": "Carol", "mail": "c@example.com"},
        )
        assert info["email"] == "c@example.com"
        assert info["avatar_url"] is None

        fallback = OAuthService._parse_userinfo(
            "microsoft",
            {"id": "ms789", "displayName": "Carol", "userPrincipalName": "carol@school.edu"},
        )
        assert fallback["email"] == "carol@school.edu"

    def test_missing_email_rejected(self):
        with pytest.raises(OAuthProviderError):
            OAuthService._parse_userinfo("google", {"sub": "g1", "name": "No Email"})

    def test_missing_user_id_rejected(self):
        with pytest.raises(OAuthProviderError):
            OAuthService._parse_userinfo("google", {"email": "x@example.com"})

    def test_unknown_provider_rejected(self):
        with pytest.raises(OAuthProviderError):
            OAuthService._parse_userinfo("apple", {"id": "1", "email": "x@example.com"})


class TestStateStorage:
    def test_store_and_consume_roundtrip(self, oauth):
        url = oauth.get_authorization_url("google", "state123", "http://localhost:8000/cb")
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
        assert "state=state123" in url
        # PKCE challenge present for Google
        assert "code_challenge=" in url and "code_challenge_method=S256" in url

        payload = oauth.consume_state("state123")
        assert payload["provider"] == "google"
        assert payload["code_verifier"]

    def test_consume_deletes_key_single_use(self, oauth):
        oauth.get_authorization_url("google", "s1", "http://localhost:8000/cb")
        assert oauth.consume_state("s1") is not None
        # B3: the state key must be gone after one use → replay is rejected.
        assert oauth.consume_state("s1") is None

    def test_unknown_state_returns_none(self, oauth):
        assert oauth.consume_state("never-stored") is None

    def test_link_intent_embedded_in_state(self, oauth):
        oauth.get_authorization_url(
            "facebook", "s2", "http://localhost:8000/cb", link_user_id="user-1", redirect_to="/profile"
        )
        payload = oauth.consume_state("s2")
        assert payload["link_user_id"] == "user-1"
        assert payload["redirect_to"] == "/profile"

    def test_facebook_skips_pkce(self, oauth):
        url = oauth.get_authorization_url("facebook", "s3", "http://localhost:8000/cb")
        assert "code_challenge" not in url

    def test_redis_down_raises_on_store(self, oauth):
        import redis as redis_lib

        class BrokenRedis(FakeRedis):
            def set(self, key, value, ex=None):
                raise redis_lib.exceptions.ConnectionError("redis down")

        oauth._redis = BrokenRedis()
        with pytest.raises(OAuthRedisUnavailableError):
            oauth.get_authorization_url("google", "s4", "http://localhost:8000/cb")

    def test_redis_down_raises_on_consume(self, oauth):
        import redis as redis_lib

        class BrokenRedis(FakeRedis):
            def get(self, key):
                raise redis_lib.exceptions.ConnectionError("redis down")

        oauth._redis = BrokenRedis()
        with pytest.raises(OAuthRedisUnavailableError):
            oauth.consume_state("s5")
