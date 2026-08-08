# ── Book Quiz — Production Image (Fly.io) ───────────────────────────
# Root-level Dockerfile referenced by fly.toml. Multi-stage build:
#   Stage 1: build the React frontend (Vite → static dist)
#   Stage 2: build the FastAPI backend + bundle frontend artifacts
#
# fly.toml runs two processes from this image:
#   app    → uvicorn app.main:app (API)
#   worker → celery -A app.worker worker (background jobs)
# ─────────────────────────────────────────────────────────────────────

# ── Stage 1: Frontend build ─────────────────────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ── Stage 2: Backend runtime ────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

# Create non-root user
RUN groupadd -r bookquiz && useradd -r -g bookquiz bookquiz

# Install Python dependencies (cached layer — requirements first)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./

# Bundle built frontend (served by CDN/nginx in production; kept in-image
# for future static serving or smoke checks)
COPY --from=frontend-builder /build/dist /app/frontend-dist

RUN chown -R bookquiz:bookquiz /app
USER bookquiz

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

# fly.toml overrides the command per process group ("app" runs uvicorn,
# "worker" runs celery). Default here matches the API process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
