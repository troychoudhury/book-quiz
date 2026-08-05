"""OAuth2 SSO orchestration for Google, Facebook, and Microsoft.

Server-side Authorization Code flow (PKCE for providers that support it).
The browser never sees provider tokens — the backend exchanges the code and
issues the app's own JWT (see issues/book-quiz-tfx.md §1.2).

State / PKCE verifier storage: Redis key ``oauth:state:{state}`` holding
``{"provider", "code_verifier", "link_user_id"?, "redirect_to"?}`` with a
10-minute TTL. The key is deleted after the callback consumes it (single use).
"""
import json
import secrets

import redis as redis_lib
import structlog
from authlib.integrations.httpx_client import OAuth2Client

from app.core.config import get_settings

logger = structlog.get_logger()

settings = get_settings()

OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes
OAUTH_STATE_KEY_PREFIX = "oauth:state:"


class OAuthRedisUnavailableError(Exception):
    """Raised when Redis cannot be reached for OAuth state storage (R3 → 503)."""


class OAuthProviderError(Exception):
    """Raised when a provider token exchange or userinfo fetch fails."""


class OAuthService:
    """Build provider authorization URLs and exchange codes for userinfo.

    Provider metadata is static per provider (documented in
    issues/book-quiz-tfx.md §5.2). A provider is only "configured" when its
    CLIENT_ID env var is set — otherwise its endpoints return 404 and its
    button is hidden on the frontend.
    """

    PROVIDERS: dict[str, dict] = {
        "google": {
            "name": "Google",
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scope": "openid email profile",
            "pkce": True,
        },
        "facebook": {
            "name": "Facebook",
            "authorize_url": "https://www.facebook.com/v19.0/dialog/oauth",
            "token_url": "https://graph.facebook.com/v19.0/oauth/access_token",
            "userinfo_url": "https://graph.facebook.com/v19.0/me?fields=id,name,email,picture",
            "scope": "email public_profile",
            # Facebook does not support PKCE for web apps; the state param
            # still protects the callback from CSRF.
            "pkce": False,
        },
        "microsoft": {
            "name": "Microsoft",
            "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "userinfo_url": "https://graph.microsoft.com/v1.0/me",
            "scope": "openid email profile User.Read",
            "pkce": True,
        },
    }

    def __init__(self) -> None:
        self._redis: redis_lib.Redis | None = None

    # ── Redis state storage ────────────────────────────────────────────

    @property
    def redis(self) -> redis_lib.Redis:
        """Lazily created Redis client (tests inject a fake via _redis)."""
        if self._redis is None:
            self._redis = redis_lib.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        return self._redis

    @staticmethod
    def _state_key(state: str) -> str:
        return f"{OAUTH_STATE_KEY_PREFIX}{state}"

    # ── Provider helpers ───────────────────────────────────────────────

    @classmethod
    def configured_providers(cls) -> list[str]:
        """Providers whose CLIENT_ID is configured (in registry order)."""
        return [name for name in cls.PROVIDERS if getattr(settings, f"{name}_client_id", "")]

    @classmethod
    def get_redirect_uri(cls, provider: str) -> str:
        """Callback URL registered with the provider."""
        base = settings.oauth_redirect_domain.rstrip("/")
        return f"{base}/api/v1/auth/oauth/{provider}/callback"

    def get_client(self, provider: str, redirect_uri: str) -> OAuth2Client:
        """Build an authlib OAuth2Client for a provider."""
        meta = self.PROVIDERS[provider]
        kwargs = {
            "client_id": getattr(settings, f"{provider}_client_id"),
            "client_secret": getattr(settings, f"{provider}_client_secret"),
            "redirect_uri": redirect_uri,
            "scope": meta["scope"],
        }
        if meta.get("pkce"):
            kwargs["code_challenge_method"] = "S256"
        if provider == "microsoft":
            # Entra ID v2 accepts client credentials in the token request body.
            kwargs["token_endpoint_auth_method"] = "client_secret_post"
        return OAuth2Client(**kwargs)

    # ── Main API ───────────────────────────────────────────────────────

    def get_authorization_url(
        self,
        provider: str,
        state: str,
        redirect_uri: str,
        link_user_id: str | None = None,
        redirect_to: str | None = None,
    ) -> str:
        """Generate a PKCE code_verifier, persist it with `state`, and return
        the provider authorization URL. Raises OAuthRedisUnavailableError if
        Redis is down (R3)."""
        meta = self.PROVIDERS[provider]
        verifier = secrets.token_urlsafe(64)
        client = self.get_client(provider, redirect_uri)
        url, _ = client.create_authorization_url(
            meta["authorize_url"],
            state=state,
            code_verifier=verifier if meta.get("pkce") else None,
        )

        payload: dict = {"provider": provider, "code_verifier": verifier}
        if link_user_id:
            # B2: linking intent is embedded in the server-side state, never
            # passed as a query param that an attacker could append.
            payload["link_user_id"] = link_user_id
        if redirect_to:
            payload["redirect_to"] = redirect_to

        self._store_state(state, payload)
        return url

    def consume_state(self, state: str) -> dict | None:
        """Fetch and delete (single-use) the OAuth state payload.

        Returns None when the state is unknown/expired. The Redis key is
        always deleted so a captured callback URL cannot be replayed (B3).
        Raises OAuthRedisUnavailableError if Redis is down (R3).
        """
        key = self._state_key(state)
        try:
            raw = self.redis.get(key)
            self.redis.delete(key)
        except redis_lib.exceptions.RedisError as exc:
            raise OAuthRedisUnavailableError("Redis unavailable for OAuth state.") from exc
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def exchange_code(self, provider: str, code: str, code_verifier: str, redirect_uri: str) -> dict:
        """Exchange the authorization code for provider tokens, fetch userinfo,
        and return a normalized identity dict:

        {"provider", "provider_user_id", "email", "name", "avatar_url"}
        """
        meta = self.PROVIDERS[provider]
        client = self.get_client(provider, redirect_uri)
        try:
            token = client.fetch_token(meta["token_url"], code=code, code_verifier=code_verifier)
            access_token = token.get("access_token")
            if not access_token:
                raise OAuthProviderError(f"{meta['name']} did not return an access token.")
            response = client.get(meta["userinfo_url"])
            response.raise_for_status()
            userinfo = response.json()
        except OAuthProviderError:
            raise
        except Exception as exc:  # network, authlib, HTTP status errors
            logger.warning("oauth.exchange_failed", provider=provider, error=str(exc))
            raise OAuthProviderError(
                f"Failed to exchange the authorization code with {meta['name']}."
            ) from exc
        return self._parse_userinfo(provider, userinfo)

    def _store_state(self, state: str, payload: dict) -> None:
        try:
            self.redis.set(self._state_key(state), json.dumps(payload), ex=OAUTH_STATE_TTL_SECONDS)
        except redis_lib.exceptions.RedisError as exc:
            raise OAuthRedisUnavailableError("Redis unavailable for OAuth state.") from exc

    @staticmethod
    def _parse_userinfo(provider: str, data: dict) -> dict:
        """Normalize provider userinfo into a common identity dict.

        Verified emails only: all three providers verify the email before
        returning it, so it can be used as the account identity anchor (Q2).
        """
        if provider == "google":
            provider_user_id = data.get("sub") or data.get("id")
            email = data.get("email")
            info = {
                "provider": provider,
                "provider_user_id": str(provider_user_id) if provider_user_id else None,
                "email": email,
                "name": data.get("name"),
                "avatar_url": data.get("picture"),
            }
        elif provider == "facebook":
            provider_user_id = data.get("id")
            email = data.get("email")
            picture = (data.get("picture") or {}).get("data") or {}
            info = {
                "provider": provider,
                "provider_user_id": str(provider_user_id) if provider_user_id else None,
                "email": email,
                "name": data.get("name"),
                "avatar_url": picture.get("url"),
            }
        elif provider == "microsoft":
            provider_user_id = data.get("id")
            # Graph returns `mail` for licensed mailboxes and
            # `userPrincipalName` otherwise.
            email = data.get("mail") or data.get("userPrincipalName")
            info = {
                "provider": provider,
                "provider_user_id": str(provider_user_id) if provider_user_id else None,
                "email": email,
                "name": data.get("displayName"),
                "avatar_url": None,
            }
        else:
            raise OAuthProviderError(f"Unknown provider: {provider}")

        if not info["provider_user_id"]:
            raise OAuthProviderError(f"{provider.title()} did not return a user id.")
        if not info["email"]:
            raise OAuthProviderError(
                f"{provider.title()} did not return an email address. "
                "An email address is required to create an account."
            )
        return info
