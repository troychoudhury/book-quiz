"""Authentication service: registration, login, token management."""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User

settings = get_settings()

# NOTE: We use the `bcrypt` library directly instead of `passlib`. passlib 1.7.4
# is incompatible with bcrypt >= 4.1 (it reads `bcrypt.__about__.__version__`,
# which was removed), causing a misleading ValueError on every hash. Direct
# bcrypt calls avoid that entire failure class.


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Raises ValueError if password is too long."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash. Returns False on any failure."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


class EmailAlreadyRegisteredError(Exception):
    """Raised when attempting to register an email that already exists."""


class AuthService:
    """Handles user authentication and JWT token operations."""

    def __init__(self, db: Session):
        self.db = db

    def register(self, email: str, password: str, display_name: str) -> User:
        """Register a new user. Raises EmailAlreadyRegisteredError if email exists."""
        normalized_email = email.strip().lower()
        existing = self.db.query(User).filter(User.email == normalized_email).first()
        if existing:
            raise EmailAlreadyRegisteredError("A user with this email already exists.")

        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            display_name=display_name.strip(),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def authenticate(self, email: str, password: str) -> User | None:
        """Authenticate a user by email and password. Returns None if invalid."""
        user = self.db.query(User).filter(User.email == email.strip().lower()).first()
        if not user or not verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return user

    def create_access_token(self, user_id: uuid.UUID) -> str:
        """Create a short-lived JWT access token with a unique jti claim."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)
        to_encode = {
            "sub": str(user_id),
            "iat": now,
            "exp": expire,
            "type": "access",
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def create_refresh_token(self, user_id: uuid.UUID) -> str:
        """Create a long-lived JWT refresh token with a unique jti claim."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=settings.refresh_token_expire_days)
        to_encode = {
            "sub": str(user_id),
            "iat": now,
            "exp": expire,
            "type": "refresh",
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def verify_token(self, token: str, expected_type: str = "access") -> uuid.UUID | None:
        """Verify a JWT token and return the user ID. Returns None if invalid."""
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            if payload.get("type") != expected_type:
                return None
            user_id = payload.get("sub")
            return uuid.UUID(user_id) if user_id else None
        except (JWTError, ValueError):
            return None

    def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch a user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()
