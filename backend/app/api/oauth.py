"""OAuth2 SSO API endpoints (Google, Facebook, Microsoft).

Routes (prefix /api/v1/auth/oauth):

- GET /providers            → configured providers (registered BEFORE /{provider}/*)
- GET /{provider}/login     → redirect to the provider's consent screen
- GET /{provider}/callback  → exchange code, find-or-create user, issue JWT

Security review fixes implemented (issues/book-quiz-tfx.md §Plan Review):
- B1: CSP ``script-src 'self'`` added in app/main.py so the fragment tokens
  cannot be exfiltrated by injected scripts.
- B2: linking intent (``link_user_id``) is stored in the Redis state payload,
  never passed as a query param an attacker could append to a victim URL.
- B3: the Redis state key is deleted after the callback consumes it
  (single-use — no replay).
- R3: OAuth endpoints return 503 when Redis is unavailable.
"""
import urllib.parse
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_optional_current_user, limiter
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.oauth_service import (
    OAuthProviderError,
    OAuthRedisUnavailableError,
    OAuthService,
)

settings = get_settings()

router = APIRouter(prefix="/api/v1/auth/oauth", tags=["oauth"])

oauth = OAuthService()


class ProviderInfo(BaseModel):
    provider: str
    name: str


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]


def _frontend_origin() -> str:
    """Origin of the frontend callback URL (e.g. http://localhost:5173)."""
    parsed = urllib.parse.urlparse(settings.oauth_frontend_callback_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _validate_redirect_to(value: str | None) -> str | None:
    """Only allow same-origin relative paths (open-redirect mitigation)."""
    if not value:
        return None
    if not value.startswith("/") or value.startswith("//") or "://" in value:
        return None
    return value


@router.get("/providers", response_model=ProvidersResponse)
def get_oauth_providers() -> ProvidersResponse:
    """List configured SSO providers (empty CLIENT_ID ⇒ provider is hidden)."""
    return ProvidersResponse(
        providers=[
            ProviderInfo(provider=name, name=OAuthService.PROVIDERS[name]["name"])
            for name in OAuthService.configured_providers()
        ]
    )


@router.get("/{provider}/login")
@limiter.limit("10/minute")
def oauth_login(
    request: Request,
    provider: str,
    redirect_to: str | None = None,
    link_account: bool = False,
    current_user: User | None = Depends(get_optional_current_user),
):
    """Initiate the OAuth flow: persist state in Redis and redirect to the
    provider. `link_account` is only honored for an authenticated user, and
    the linking intent is embedded in the server-side state (B2)."""
    if provider not in OAuthService.configured_providers():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider}' is not configured.",
        )

    state = uuid.uuid4().hex
    safe_redirect_to = _validate_redirect_to(redirect_to)

    link_user_id: str | None = None
    if link_account:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="You must be logged in to link an account.",
            )
        link_user_id = str(current_user.id)

    try:
        url = oauth.get_authorization_url(
            provider,
            state,
            OAuthService.get_redirect_uri(provider),
            link_user_id=link_user_id,
            redirect_to=safe_redirect_to,
        )
    except OAuthRedisUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable. Please try again later.",
        )
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get("/{provider}/callback")
@limiter.limit("10/minute")
def oauth_callback(
    request: Request,
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Handle the provider redirect: exchange the code, find-or-create the
    user (auto-linking by verified email), issue a JWT, and send the browser
    to the frontend callback page with the tokens in the URL fragment."""
    if provider not in OAuthService.configured_providers():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider}' is not configured.",
        )

    # User denied consent or provider-level failure → friendly frontend error.
    if error:
        frontend_error = urllib.parse.quote(error)
        return RedirectResponse(
            f"{_frontend_origin()}/login?error={frontend_error}",
            status_code=status.HTTP_302_FOUND,
        )

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state parameter.",
        )

    try:
        payload = oauth.consume_state(state)
    except OAuthRedisUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable. Please try again later.",
        )
    if payload is None or payload.get("provider") != provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="State mismatch. Possible CSRF.",
        )

    try:
        info = oauth.exchange_code(
            provider,
            code,
            payload["code_verifier"],
            OAuthService.get_redirect_uri(provider),
        )
    except OAuthProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    auth = AuthService(db)
    redirect_to = _validate_redirect_to(payload.get("redirect_to"))

    # ── Link-account flow (B2): bind provider to the initiating user ───
    if payload.get("link_user_id"):
        user = auth.get_user_by_id(uuid.UUID(payload["link_user_id"]))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The account to link was not found or is inactive.",
            )
        auth.link_oauth_provider(
            user.id,
            provider,
            info["provider_user_id"],
            info["email"],
            info.get("name"),
            info.get("avatar_url"),
        )
        destination = redirect_to or "/profile"
        return RedirectResponse(
            f"{_frontend_origin()}{destination}",
            status_code=status.HTTP_302_FOUND,
        )

    # ── Login flow ─────────────────────────────────────────────────────
    user = _find_or_create_user(auth, provider, info)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The account associated with this provider is inactive.",
        )

    fragment = urllib.parse.urlencode(
        {
            "access_token": auth.create_access_token(user.id),
            "refresh_token": auth.create_refresh_token(user.id),
            "token_type": "bearer",
            "redirect_to": redirect_to or "/",
        }
    )
    return RedirectResponse(
        f"{settings.oauth_frontend_callback_url}#{fragment}",
        status_code=status.HTTP_302_FOUND,
    )


def _find_or_create_user(auth: AuthService, provider: str, info: dict) -> User | None:
    """Resolve the user for an SSO login.

    Priority:
    1. Existing link row for (provider, provider_user_id) — the authoritative
       identity anchor and the "log in after signup" path.
    2. Existing user with the same verified email — auto-link (Q3).
    3. Otherwise create a new SSO-only account.
    """
    link = auth.find_oauth_link(provider, info["provider_user_id"])
    if link:
        return auth.get_user_by_id(link.user_id)

    user = auth.get_user_by_email(info["email"])
    if user is not None:
        auth.link_oauth_provider(
            user.id,
            provider,
            info["provider_user_id"],
            info["email"],
            info.get("name"),
            info.get("avatar_url"),
        )
        return user

    user = auth.create_user_from_oauth(
        email=info["email"],
        name=info.get("name"),
        avatar_url=info.get("avatar_url"),
    )
    auth.link_oauth_provider(
        user.id,
        provider,
        info["provider_user_id"],
        info["email"],
        info.get("name"),
        info.get("avatar_url"),
    )
    return user
