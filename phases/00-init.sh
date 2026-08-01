#!/usr/bin/env bash
#==============================================================================
# Phase 00: Project Initialization & Development Tooling
#==============================================================================
# Sets up:
#   - Python backend (FastAPI) with venv, pytest, ruff, mypy
#   - React frontend (TypeScript) with Vite, ESLint, Prettier, Vitest
#   - PostgreSQL database schema & migrations (Alembic)
#   - Docker Compose for reproducible dev environment
#   - Pre-commit hooks
#   - Git configuration
#==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

info()  { echo -e "\033[0;34m[INIT]\033[0m  $*"; }
ok()    { echo -e "\033[0;32m[OK]\033[0m    $*"; }
err()   { echo -e "\033[0;31m[ERROR]\033[0m $*"; }

info "Setting up reproducible development environment..."

# --- Backend Setup -------------------------------------------------
setup_backend() {
    info "Setting up Python backend (FastAPI)..."
    cd "$PROJECT_ROOT"

    # Create backend directory structure
    mkdir -p backend/app/{api,models,services,schemas,core}
    mkdir -p backend/tests/{unit,integration,acceptance}
    mkdir -p backend/alembic/versions

    # Python virtual environment
    python3 -m venv backend/.venv
    source backend/.venv/bin/activate

    # Requirements
    cat > backend/requirements.txt << 'PYREQ'
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
alembic==1.14.0
psycopg2-binary==2.9.10
pydantic==2.10.3
pydantic-settings==2.7.0
httpx==0.28.1
openai==1.58.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.18
isbntools==4.14.4
celery==5.4.0
redis==5.2.1
PYREQ

    # Dev requirements
    cat > backend/requirements-dev.txt << 'DEVREQ'
pytest==8.3.4
pytest-cov==6.0.0
pytest-asyncio==0.25.0
pytest-xdist==3.6.1
ruff==0.8.4
mypy==1.13.0
black==24.10.0
httpx==0.28.1
factory-boy==3.3.1
faker==33.1.0
DEVREQ

    pip install -r backend/requirements.txt -r backend/requirements-dev.txt --quiet

    # Ruff config
    cat > backend/ruff.toml << 'RUFF'
target-version = "py312"
line-length = 100
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM", "TCH"]
ignore = ["E501"]
[format]
quote-style = "double"
indent-style = "space"
RUFF

    # Mypy config
    cat > backend/mypy.ini << 'MYPY'
[mypy]
python_version = 3.12
strict = true
ignore_missing_imports = true
plugins = pydantic.mypy
MYPY

    # Alembic config
    cat > backend/alembic.ini << 'ALEMBIC'
[alembic]
script_location = alembic
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic
[handlers]
keys = console
[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
ALEMBIC

    deactivate
    ok "Backend setup complete."
}

# --- Frontend Setup ------------------------------------------------
setup_frontend() {
    info "Setting up React frontend (TypeScript + Vite)..."
    cd "$PROJECT_ROOT"

    # Create Vite React TypeScript project
    npm create vite@latest frontend -- --template react-ts 2>&1 | tail -1 || true
    cd frontend

    # Install dependencies
    npm install --save-dev \
        @testing-library/react @testing-library/jest-dom @testing-library/user-event \
        vitest @vitest/coverage-v8 jsdom \
        eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin \
        prettier eslint-config-prettier eslint-plugin-react eslint-plugin-react-hooks \
        msw playwright @playwright/test

    npm install react-router-dom @tanstack/react-query axios zustand

    # ESLint config
    cat > .eslintrc.cjs << 'ESLINT'
module.exports = {
  root: true,
  env: { browser: true, es2024: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
    'prettier',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['react', '@typescript-eslint'],
  rules: {
    'react/react-in-jsx-scope': 'off',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
  },
  settings: { react: { version: 'detect' } },
};
ESLINT

    # Prettier config
    cat > .prettierrc << 'PRETTIER'
{
  "semi": true,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2
}
PRETTIER

    # Vitest config (append to vite.config.ts)
    cat > vitest.config.ts << 'VITEST'
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      thresholds: { lines: 80, branches: 70, functions: 80, statements: 80 },
    },
  },
});
VITEST

    # Test setup
    mkdir -p src/test
    cat > src/test/setup.ts << 'SETUP'
import '@testing-library/jest-dom';
SETUP

    ok "Frontend setup complete."
}

# --- Docker Setup --------------------------------------------------
setup_docker() {
    info "Setting up Docker Compose for reproducible dev environment..."
    cd "$PROJECT_ROOT"

    cat > docker-compose.yml << 'DOCKER'
version: "3.9"
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: bookquiz
      POSTGRES_USER: bookquiz
      POSTGRES_PASSWORD: bookquiz_dev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bookquiz"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
    environment:
      DATABASE_URL: postgresql://bookquiz:bookquiz_dev@db:5432/bookquiz
      REDIS_URL: redis://redis:6379/0
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      VITE_API_URL: http://localhost:8000
    depends_on:
      - backend
    command: npm run dev -- --host 0.0.0.0

volumes:
  pgdata:
DOCKER

    # Backend dev Dockerfile
    mkdir -p backend
    cat > backend/Dockerfile.dev << 'DOCKERDEV'
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
DOCKERDEV

    # Frontend dev Dockerfile
    mkdir -p frontend
    cat > frontend/Dockerfile.dev << 'DOCKERFE'
FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
DOCKERFE

    ok "Docker Compose setup complete."
}

# --- Pre-commit Hooks ----------------------------------------------
setup_precommit() {
    info "Setting up pre-commit hooks..."
    cd "$PROJECT_ROOT"

    cat > .pre-commit-config.yaml << 'PRECOMMIT'
repos:
  - repo: local
    hooks:
      - id: ruff
        name: ruff (backend)
        entry: bash -c 'cd backend && ruff check . && ruff format --check .'
        language: system
        files: ^backend/.*\.py$
        pass_filenames: false

      - id: mypy
        name: mypy (backend)
        entry: bash -c 'cd backend && mypy app/'
        language: system
        files: ^backend/.*\.py$
        pass_filenames: false

      - id: eslint
        name: eslint (frontend)
        entry: bash -c 'cd frontend && npx eslint . --ext .ts,.tsx'
        language: system
        files: ^frontend/.*\.(ts|tsx)$
        pass_filenames: false

      - id: prettier
        name: prettier (frontend)
        entry: bash -c 'cd frontend && npx prettier --check .'
        language: system
        files: ^frontend/.*\.(ts|tsx|json|css)$
        pass_filenames: false

      - id: pytest
        name: pytest (backend)
        entry: bash -c 'cd backend && python -m pytest tests/ -x --tb=short'
        language: system
        files: ^backend/.*\.py$
        pass_filenames: false
        stages: [pre-push]

      - id: vitest
        name: vitest (frontend)
        entry: bash -c 'cd frontend && npx vitest run'
        language: system
        files: ^frontend/.*\.(ts|tsx)$
        pass_filenames: false
        stages: [pre-push]
PRECOMMIT

    ok "Pre-commit hooks configured."
}

# --- Makefile ------------------------------------------------------
setup_makefile() {
    info "Creating Makefile for common commands..."
    cd "$PROJECT_ROOT"

    cat > Makefile << 'MAKEFILE'
.PHONY: dev test lint format clean db-up db-down migrate

# ── Development ──────────────────────────────────────────
dev:
	docker compose up -d db redis
	cd backend && .venv/bin/uvicorn app.main:app --reload &
	cd frontend && npm run dev &
	@echo "Backend: http://localhost:8000 | Frontend: http://localhost:5173"

dev-docker:
	docker compose up --build

# ── Testing ──────────────────────────────────────────────
test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/pytest tests/ -v --cov=app --cov-report=term-missing

test-frontend:
	cd frontend && npx vitest run --coverage

test-e2e:
	cd frontend && npx playwright test

# ── Linting & Formatting ─────────────────────────────────
lint: lint-backend lint-frontend

lint-backend:
	cd backend && .venv/bin/ruff check . && .venv/bin/mypy app/

lint-frontend:
	cd frontend && npx eslint . --ext .ts,.tsx && npx prettier --check .

format:
	cd backend && .venv/bin/ruff format .
	cd frontend && npx prettier --write .

# ── Database ─────────────────────────────────────────────
db-up:
	docker compose up -d db redis

db-down:
	docker compose down

migrate:
	cd backend && .venv/bin/alembic upgrade head

migrate-new:
	cd backend && .venv/bin/alembic revision --autogenerate -m "$(msg)"

# ── Cleanup ──────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.venv frontend/dist .logs
MAKEFILE

    ok "Makefile created."
}

# --- Main ----------------------------------------------------------
main() {
    info "=== Phase 00: Project Initialization ==="
    setup_backend
    setup_frontend
    setup_docker
    setup_precommit
    setup_makefile

    ok "Phase 00 complete. Project is initialized and reproducible."
    echo ""
    echo "  Quick start:"
    echo "    make dev           # Start development servers"
    echo "    make test          # Run all tests"
    echo "    make lint          # Run linters"
    echo "    docker compose up  # Full Docker environment"
}

main "$@"
