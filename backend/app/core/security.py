"""Security dependencies: JWT auth extraction and rate limiting."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.services.auth_service import AuthService

settings = get_settings()

# Shared rate limiter (Redis-backed in production; in-memory is fine for dev).
# `enabled` is driven by settings so tests can disable it via RATE_LIMIT_ENABLED=false.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
    storage_uri="memory://",
    enabled=settings.rate_limit_enabled,
)

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency that resolves the authenticated user from the JWT.

    Raises 401 if the Authorization header is missing or the token is invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a valid access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth = AuthService(db)
    user_id = auth.verify_token(credentials.credentials, expected_type="access")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of raising for guests."""
    if credentials is None:
        return None
    auth = AuthService(db)
    user_id = auth.verify_token(credentials.credentials, expected_type="access")
    if user_id is None:
        return None
    return auth.get_user_by_id(user_id)


def rate_limit_check(request: Request) -> str:
    """Return a stable key for rate limiting (IP address)."""
    return get_remote_address(request)
