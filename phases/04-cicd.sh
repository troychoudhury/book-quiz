#!/usr/bin/env bash
#==============================================================================
# Phase 04: CI/CD Pipeline
#==============================================================================
# Sets up:
#   - GitHub Actions CI workflow (lint, test, type-check, E2E)
#   - CD workflow (Docker build, push, deploy)
#   - Fly.io / Railway deployment configuration
#==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info()  { echo -e "\033[0;34m[CICD]\033[0m  $*"; }
ok()    { echo -e "\033[0;32m[OK]\033[0m    $*"; }

# --- CI Workflow --------------------------------------------------
setup_ci_workflow() {
    info "Creating CI workflow..."
    mkdir -p "$SCRIPT_DIR/.github/workflows"

    cat > "$SCRIPT_DIR/.github/workflows/ci.yml" << 'EOF'
name: CI — Lint, Test, Type Check

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "22"

jobs:
  # ── Backend CI ──────────────────────────────────────────────────
  backend:
    name: Backend — Lint & Test
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: bookquiz_test
          POSTGRES_USER: bookquiz
          POSTGRES_PASSWORD: test_pass
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 5

    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
          cache-dependency-path: backend/requirements*.txt

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt -r requirements-dev.txt

      - name: Ruff — Lint & Format Check
        run: |
          ruff check app/ tests/
          ruff format --check app/ tests/

      - name: Mypy — Type Check
        run: mypy app/ --ignore-missing-imports

      - name: Pytest — Unit & Integration Tests
        env:
          DATABASE_URL: postgresql://bookquiz:test_pass@localhost:5432/bookquiz_test
          REDIS_URL: redis://localhost:6379/0
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          pytest tests/ -v --tb=short \
            --cov=app --cov-report=term-missing --cov-report=xml \
            --cov-fail-under=80 \
            -n auto

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v5
        with:
          files: backend/coverage.xml
          flags: backend
        continue-on-error: true

  # ── Frontend CI ─────────────────────────────────────────────────
  frontend:
    name: Frontend — Lint, Type Check & Test
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: ESLint
        run: npx eslint . --ext .ts,.tsx --max-warnings 0

      - name: Prettier — Format Check
        run: npx prettier --check .

      - name: TypeScript — Type Check
        run: npx tsc --noEmit

      - name: Vitest — Unit & Integration Tests
        run: npx vitest run --coverage

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v5
        with:
          files: frontend/coverage/lcov.info
          flags: frontend
        continue-on-error: true

  # ── E2E Tests ───────────────────────────────────────────────────
  e2e:
    name: E2E — Playwright
    runs-on: ubuntu-latest
    needs: [backend, frontend]
    timeout-minutes: 20
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: bookquiz_e2e
          POSTGRES_USER: bookquiz
          POSTGRES_PASSWORD: e2e_pass
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}

      - name: Install backend
        working-directory: backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Install frontend
        working-directory: frontend
        run: npm ci

      - name: Install Playwright
        working-directory: frontend
        run: npx playwright install --with-deps chromium

      - name: Start backend
        working-directory: backend
        env:
          DATABASE_URL: postgresql://bookquiz:e2e_pass@localhost:5432/bookquiz_e2e
        run: |
          uvicorn app.main:app --host 0.0.0.0 --port 8000 &
          sleep 3

      - name: Start frontend
        working-directory: frontend
        run: |
          npx vite --port 5173 --host 0.0.0.0 &
          sleep 3

      - name: Run Playwright E2E tests
        working-directory: frontend
        run: npx playwright test

      - name: Upload Playwright report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: frontend/playwright-report/

  # ── Security Scan ───────────────────────────────────────────────
  security:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Snyk — Backend
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          args: --severity-threshold=medium
        continue-on-error: true

      - name: Snyk — Frontend
        uses: snyk/actions/node@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          args: --severity-threshold=medium
        continue-on-error: true

  # ── All Clear Gate ──────────────────────────────────────────────
  all-clear:
    name: All CI Gates Passed
    needs: [backend, frontend, e2e]
    runs-on: ubuntu-latest
    steps:
      - name: ✅ CI Pipeline Complete
        run: echo "All CI gates passed. Ready for deployment."
EOF
    ok "CI workflow created."
}

# --- CD Workflow --------------------------------------------------
setup_cd_workflow() {
    info "Creating CD workflow..."

    cat > "$SCRIPT_DIR/.github/workflows/cd.yml" << 'EOF'
name: CD — Build & Deploy

on:
  push:
    branches: [main]
    paths-ignore:
      - 'docs/**'
      - '*.md'
      - '.github/workflows/ci.yml'
  workflow_dispatch:

env:
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "22"

jobs:
  # ── Run CI First ────────────────────────────────────────────────
  ci-gate:
    uses: ./.github/workflows/ci.yml
    secrets: inherit

  # ── Build & Push Docker Images ──────────────────────────────────
  build:
    name: Build & Push Docker Images
    needs: ci-gate
    runs-on: ubuntu-latest
    strategy:
      matrix:
        component: [backend, frontend]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}/${{ matrix.component }}
          tags: |
            type=sha,prefix=,format=short
            type=ref,event=branch
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: ./${{ matrix.component }}
          file: ./${{ matrix.component }}/Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ── Database Migrations ─────────────────────────────────────────
  migrate:
    name: Run Database Migrations
    needs: [build]
    runs-on: ubuntu-latest
    environment: production

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Run Alembic migrations
        working-directory: backend
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          pip install alembic psycopg2-binary
          alembic upgrade head

  # ── Deploy to Fly.io ────────────────────────────────────────────
  deploy:
    name: Deploy to Fly.io
    needs: [migrate]
    runs-on: ubuntu-latest
    environment: production
    concurrency: production

    steps:
      - uses: actions/checkout@v4

      - name: Set up Fly.io CLI
        uses: superfly/flyctl-actions/setup-flyctl@master

      - name: Deploy
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
        run: flyctl deploy --remote-only

      - name: Health Check
        run: |
          for i in $(seq 1 10); do
            STATUS=$(curl -s -o /dev/null -w '%{http_code}' https://${{ vars.APP_URL }}/api/v1/health)
            if [ "$STATUS" = "200" ]; then
              echo "✅ Health check passed"
              exit 0
            fi
            echo "⏳ Waiting... attempt $i/10 (got $STATUS)"
            sleep 6
          done
          echo "❌ Health check failed after 10 attempts"
          exit 1

  # ── Smoke Tests ─────────────────────────────────────────────────
  smoke:
    name: Post-Deploy Smoke Tests
    needs: [deploy]
    runs-on: ubuntu-latest

    steps:
      - name: Run smoke tests
        run: |
          BASE="${{ vars.APP_URL }}"
          echo "Testing $BASE..."

          # Health check
          curl -fsS "$BASE/api/v1/health" | jq .status

          # Book search
          curl -fsS "$BASE/api/v1/books?q=harry" | jq '.items | length'

          echo "✅ Smoke tests passed"
EOF
    ok "CD workflow created."
}

# --- Docker Production Files --------------------------------------
setup_docker_production() {
    info "Creating production Dockerfiles..."

    cat > "$SCRIPT_DIR/backend/Dockerfile" << 'EOF'
# ── Build stage ───────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

# Create non-root user
RUN groupadd -r bookquiz && useradd -r -g bookquiz bookquiz

COPY --from=builder /root/.local /home/bookquiz/.local
COPY . .

# Ensure scripts in .local are usable
ENV PATH=/home/bookquiz/.local/bin:$PATH

RUN chown -R bookquiz:bookquiz /app
USER bookquiz

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

    cat > "$SCRIPT_DIR/frontend/Dockerfile" << 'EOF'
# ── Build stage ───────────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ── Serve stage ───────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:80/ || exit 1
EOF

    cat > "$SCRIPT_DIR/frontend/nginx.conf" << 'EOF'
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Gzip
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 256;

    # Security headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self' https:;" always;

    # SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Proxy API requests to backend
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 10s;
        proxy_read_timeout 60s;
    }
}
EOF
    ok "Production Dockerfiles created."
}

# --- Fly.io Config ------------------------------------------------
setup_fly_config() {
    info "Creating Fly.io configuration..."

    cat > "$SCRIPT_DIR/fly.toml" << 'EOF'
app = "book-quiz"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[[services]]
  protocol = "tcp"
  internal_port = 8000
  processes = ["app"]

  [[services.ports]]
    port = 80
    handlers = ["http"]
    force_https = true

  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]

  [[services.http_checks]]
    interval = "15s"
    timeout = "5s"
    grace_period = "10s"
    method = "get"
    path = "/api/v1/health"
    protocol = "http"

[env]
  ENVIRONMENT = "production"
  DATABASE_URL = ""  # Set via `fly secrets set DATABASE_URL=...`
  REDIS_URL = ""     # Set via `fly secrets set REDIS_URL=...`
  JWT_SECRET_KEY = "" # Set via `fly secrets set JWT_SECRET_KEY=...`
  OPENAI_API_KEY = "" # Set via `fly secrets set OPENAI_API_KEY=...`

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"

[processes]
  app = "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"
  worker = "celery -A app.worker worker --loglevel=info --concurrency 2"
EOF

    ok "Fly.io configuration created."
}

# --- Main ----------------------------------------------------------
main() {
    info "=== Phase 04: CI/CD Pipeline ==="

    setup_ci_workflow
    setup_cd_workflow
    setup_docker_production
    setup_fly_config

    ok "Phase 04 complete. CI/CD pipelines configured."
    echo ""
    echo "  Generated:"
    echo "    .github/workflows/ci.yml  — Lint, test, type-check, E2E on PR/main"
    echo "    .github/workflows/cd.yml  — Docker build, push, deploy, smoke tests"
    echo "    backend/Dockerfile        — Production Python image"
    echo "    frontend/Dockerfile       — Production Nginx + SPA image"
    echo "    frontend/nginx.conf       — Nginx config with API proxy"
    echo "    fly.toml                  — Fly.io deployment config"
    echo ""
    echo "  Required secrets (set in GitHub → Settings → Secrets):"
    echo "    OPENAI_API_KEY"
    echo "    DATABASE_URL"
    echo "    REDIS_URL"
    echo "    JWT_SECRET_KEY"
    echo "    FLY_API_TOKEN"
    echo "    SNYK_TOKEN (optional, for security scanning)"
}

main "$@"
