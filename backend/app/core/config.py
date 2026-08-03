"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Secrets have NO default values — they must be provided via environment
    variables (or a .env file). The application refuses to start in production
    without them (see app/main.py startup validation).
    """

    # Application
    app_name: str = "Book Quiz API"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # Database — credentials must come from DATABASE_URL env var in real
    # deployments; the default here only targets a local dev container.
    database_url: str = "postgresql://bookquiz:bookquiz_dev@localhost:5432/bookquiz"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth — NO default secret. Must be set via env var.
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # OpenAI / LLM
    openai_api_key: str = ""
    openai_base_url: str = ""  # Empty = use OpenAI default; set for DeepSeek etc.
    openai_model: str = "gpt-4o-mini"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Admin — NO default key. Must be set via env var.
    admin_api_key: str = ""

    # Rate limiting
    rate_limit_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def validate_for_environment(self) -> None:
        """Validate that required secrets are present.

        Called at application startup. Raises RuntimeError if a required
        secret is missing so the app fails fast instead of running with
        known-insecure defaults.
        """
        if self.environment == "production":
            missing = []
            if not self.jwt_secret_key:
                missing.append("JWT_SECRET_KEY")
            if not self.admin_api_key:
                missing.append("ADMIN_API_KEY")
            if "bookquiz_dev" in self.database_url or "@" not in self.database_url:
                missing.append("DATABASE_URL (must include credentials)")
            if missing:
                raise RuntimeError(
                    f"Refusing to start in production: missing required "
                    f"environment variables: {', '.join(missing)}"
                )


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
