"""FastAPI application entry point."""
import logging
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from structlog.typing import Processor

from app.core.config import get_settings
from app.core.security import limiter
from app.api import auth, books, profile, quiz, admin

settings = get_settings()


def configure_logging() -> None:
    """Configure structlog for structured logging.

    Development: human-readable console output.
    Production: JSON lines for log aggregation.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.environment == "production":
        processors: list[Processor] = shared_processors + [structlog.processors.JSONRenderer()]
    else:
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.INFO if not settings.debug else logging.DEBUG
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Fail fast in production when required secrets are missing.
    settings.validate_for_environment()
    logger = structlog.get_logger()
    logger.info("app.starting", environment=settings.environment)
    yield
    logger.info("app.stopping")


configure_logging()
logger = structlog.get_logger()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Rate limiting
def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """Return a consistent 429 response for rate limit violations."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again."},
        headers={"Retry-After": "60"},
    )


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Prevent caching of sensitive responses
    if request.url.path.startswith("/api/v1/auth"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add a unique request ID header and log request completion."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    elapsed = time.monotonic() - start
    logger.info(
        "request.completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        elapsed_ms=round(elapsed * 1000),
    )
    return response


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions without leaking internals to clients."""
    logger.error(
        "unhandled_error",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
        request_id=getattr(request.state, "request_id", "unknown"),
    )
    if settings.debug:
        # In debug mode, include details to help local development.
        content = {"detail": "An unexpected error occurred.", "error_type": type(exc).__name__}
    else:
        # In production, never leak internal exception class names.
        content = {"detail": "An unexpected error occurred."}
    return JSONResponse(status_code=500, content=content)


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": settings.app_version}

app.include_router(auth.router)
app.include_router(books.router)
app.include_router(quiz.router)
app.include_router(profile.router)
app.include_router(admin.router)
