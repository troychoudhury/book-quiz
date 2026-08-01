"""Authentication service: registration, login, token management."""
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Handles user authentication and JWT token operations."""

    def __init__(self, db: Session):
        self.db = db

    def register(self, email: str, password: str, display_name: str) -> User:
        """Register a new user. Raises ValueError if email exists."""
        existing = self.db.query(User).filter(User.email == email).first()
        if existing:
            raise ValueError("A user with this email already exists.")

        user = User(
            email=email,
            password_hash=pwd_context.hash(password),
            display_name=display_name,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def authenticate(self, email: str, password: str) -> User | None:
        """Authenticate a user by email and password. Returns None if invalid."""
        user = self.db.query(User).filter(User.email == email).first()
        if not user or not pwd_context.verify(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return user

    def create_access_token(self, user_id: uuid.UUID) -> str:
        """Create a short-lived JWT access token."""
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        to_encode = {"sub": str(user_id), "exp": expire, "type": "access"}
        return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def create_refresh_token(self, user_id: uuid.UUID) -> str:
        """Create a long-lived JWT refresh token."""
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        to_encode = {"sub": str(user_id), "exp": expire, "type": "refresh"}
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
