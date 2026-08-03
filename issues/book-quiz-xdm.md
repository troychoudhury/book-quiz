# dev: developer tooling CLI for local development

**Bead**:  | **Status**: 

## Description

## Problem

Currently there is no standardized way to set up and run the development environment. Developers must manually:
- Create venv, install Python deps
- Install Node deps
- Start backend, frontend, database, and Redis separately
- Remember environment variables for each service
- Manually run migrations

This is error-prone, slow, and differs from production deployment. The setup documented above (SQLite + manual uvicorn + manual vite) does not match production (PostgreSQL + Redis + Celery + Docker).

## Proposed Solution

A `dev` CLI tool (shell script or Makefile-based) at the repo root that provides:

### `dev setup`
First-time setup. Idempotent — safe to run multiple times.
- Creates Python venv if missing, installs requirements.txt + requirements-dev.txt
- Runs `npm ci` in frontend/
- Copies `.env.example` → `.env` if not present (with generated dev secrets)
- Initializes git pre-commit hooks
- Creates Docker volumes/networks for local dev
- Runs database migrations
- Prints success message with next steps

### `dev up`
Bring up the **full stack** mirroring production as closely as possible:
- Starts PostgreSQL container (same version as production: 16-alpine)
- Starts Redis container (same version as production: 7-alpine)
- Runs database migrations (Alembic)
- Starts Celery worker (for background AI jobs)
- Starts backend (uvicorn with --reload for hot reload)
- Starts frontend (Vite dev server with HMR)
- All services use `.env` for configuration
- Handles port conflicts gracefully
- Shows service status on startup

### `dev down`
Graceful teardown:
- Stops all containers and processes
- Removes containers but **preserves volumes** (data survives)
- Option: `dev down --volumes` to also wipe database data

### `dev test`
Run end-to-end tests in an environment matching production:
- `dev test` — runs all tests (backend unit, backend integration, frontend unit, E2E)
- `dev test --unit` — unit tests only
- `dev test --e2e` — Playwright E2E tests only
- `dev test --coverage` — with coverage reports
- Ensures test database is isolated from dev database

### Additional Suggested Commands

| Command | Description |
|---------|-------------|
| `dev lint` | Run all linters (ruff, mypy, eslint, prettier) |
| `dev format` | Auto-format code (ruff format, prettier --write) |
| `dev db-migrate` | Run Alembic migrations |
| `dev db-migrate-new "msg"` | Create a new Alembic migration |
| `dev db-reset` | Drop and recreate database (with confirmation) |
| `dev db-seed` | Seed database with sample books/questions for testing |
| `dev logs [service]` | Tail logs from a specific service or all services |
| `dev ps` | Show status of all services |
| `dev shell <service>` | Open a shell in a running container |
| `dev build` | Build production Docker images |
| `dev clean` | Remove all containers, volumes, venv, node_modules, build artifacts |
| `dev doctor` | Diagnose common issues (missing deps, port conflicts, env vars) |

## Acceptance Criteria

1. `git clone <repo> && cd book-quiz && ./dev setup && ./dev up` results in a fully working local environment
2. `curl http://localhost:8000/api/v1/health` returns 200
3. `curl http://localhost:5173/` returns the React app
4. `dev test` passes all tests
5. `dev down` stops everything cleanly
6. `.env` is the ONLY difference between local and production configuration
7. Works on macOS and Linux (Docker required)

## Design Considerations

- Use `docker compose` for PostgreSQL, Redis, and Celery worker
- Backend and frontend can run natively (faster iteration) or in containers (closer to prod)
- Provide both options: `dev up --native` (faster) vs `dev up --docker` (production-like)
- All secrets/config in `.env` — NEVER committed to git
- `.env.example` committed with placeholder values and documentation
- `dev` script should be a single-file bash script at repo root for discoverability
- Colored output and clear error messages
- Should detect missing dependencies (Python, Node, Docker) and provide install instructions

## Dependencies

- Requires `docker compose` for database and cache
- Blocks: book-quiz-3c4 (database schema), book-quiz-op6 (auth system)

## Agent Log

| Date | Agent | Action | Summary |
|------|-------|--------|----------|
| 2026-08-03T01:05:23Z | system | created | Issue filed |

## Architecture Plan

**Author**: architect (synthesized) | **Date**: 2026-08-03

### Component Diagram

```
┌─────────────────────────────────────────────────────┐
│                    ./dev script                      │
│  (single bash script at repo root, ~600 lines)      │
├─────────────────────────────────────────────────────┤
│  Command dispatch: setup | up | down | test | ...   │
├─────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Docker   │  │ Python   │  │ Node.js          │  │
│  │ Compose  │  │ venv     │  │ npm              │  │
│  │ (DB/Redis│  │ (backend)│  │ (frontend)       │  │
│  │  Celery) │  │          │  │                  │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Design Decisions

**ADR-dev-001: Bash script over Makefile**
- **Decision**: Single `dev` bash script at repo root
- **Rationale**: More flexible than Makefile (conditionals, colored output, dependency detection). Single file for discoverability. No additional build tools needed — bash is universal on macOS/Linux.

**ADR-dev-002: Dual-mode operation (native vs docker)**
- **Decision**: `dev up` defaults to native mode (backend + frontend run on host, DB + Redis in Docker). `dev up --docker` runs everything in containers.
- **Rationale**: Native mode gives faster iteration (hot reload, no rebuild). Docker mode provides production parity for debugging deployment issues.
- **Native mode**: PostgreSQL + Redis + Celery in Docker. Backend (uvicorn --reload) and frontend (Vite HMR) on host.
- **Docker mode**: All 6 services in Docker Compose, matching `docker-compose.yml` + `fly.toml`.

**ADR-dev-003: `.env` as single source of config truth**
- **Decision**: All service configuration (ports, DB URLs, secrets) flows from `.env`. Production overrides via `fly secrets set`.
- **Rationale**: `.env` is the ONLY documented diff between local and production.

### `dev up` Flow

```
1. Load .env, validate required vars
2. Check dependencies: docker, python3, node
3. Start Docker services (db, redis) via `docker compose up -d`
4. Wait for health checks (pg_isready, redis-cli ping)
5. Run Alembic migrations: `cd backend && alembic upgrade head`
6. [Native] Start Celery worker: `cd backend && celery -A app.worker worker`
7. [Native] Start backend: `cd backend && uvicorn app.main:app --reload`
8. [Native] Start frontend: `cd frontend && vite --host`
9. [Docker] Start all: `docker compose up -d --build`
10. Print service URLs and health status
```

### `dev down` Flow

```
1. [Native] Kill background processes: uvicorn, vite, celery
2. Stop Docker containers: `docker compose down`
3. [--volumes] Remove volumes: `docker compose down -v`
```

### File Structure

```
repo-root/
├── dev                    # ← THE SCRIPT (single file)
├── .env                  # generated by dev setup, gitignored
├── .env.example          # committed template with placeholders
├── docker-compose.yml    # production-mirroring compose file
├── backend/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── requirements.txt
└── frontend/
    ├── Dockerfile
    └── package.json
```

### `.env.example` Design

```bash
# ── Local Development ────────────────────────────
ENVIRONMENT=development
DEBUG=true

# ── Database ─────────────────────────────────────
DATABASE_URL=postgresql://bookquiz:bookquiz_dev@localhost:5432/bookquiz

# ── Redis ────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── Auth (generate with: openssl rand -hex 32) ──
JWT_SECRET_KEY=change-me-in-production

# ── OpenAI (required for question generation) ───
OPENAI_API_KEY=sk-your-key-here

# ── Admin ────────────────────────────────────────
ADMIN_API_KEY=admin-dev-key-change-me

# ── Rate Limiting ────────────────────────────────
RATE_LIMIT_ENABLED=true
```

### Command Reference

| Command | Implementation |
|---------|---------------|
| `setup` | Creates venv (`python3 -m venv`), `npm ci`, copies `.env.example`, `docker compose` volume init, `alembic upgrade head`, `pre-commit install` |
| `up [--native\|--docker]` | Docker Compose for infra, then native or containerized app layer |
| `down [--volumes]` | Kill native processes, `docker compose down` |
| `test [--unit\|--e2e\|--coverage]` | `pytest` + `vitest run` + `playwright test` |
| `lint` | `ruff check` + `mypy` + `eslint` + `prettier --check` |
| `format` | `ruff format` + `prettier --write` |
| `db-migrate` | `cd backend && alembic upgrade head` |
| `db-migrate-new "msg"` | `cd backend && alembic revision --autogenerate -m "msg"` |
| `db-reset` | `docker compose down -v && docker compose up -d db && alembic upgrade head` |
| `db-seed` | Run seed script (stub — requires hydration pipeline) |
| `logs [svc]` | `docker compose logs -f [svc]` + native process logs |
| `ps` | `docker compose ps` + native process status |
| `build` | `docker compose build` |
| `clean` | `docker compose down -v`, remove `.venv`, `node_modules`, `__pycache__`, `dev.db` |
| `doctor` | Check: docker, python3, node, port conflicts, `.env` exists, venv exists |

### Dependencies

- **Docker + Docker Compose v2** — required (provides PostgreSQL + Redis)
- **Python 3.12+** — required for backend
- **Node.js 22+** — required for frontend
- **jq** — optional (for JSON parsing in `dev ps`)

### Error Handling

- Each command validates prerequisites before running
- Missing Docker: prints install URL for the detected OS
- Missing Python/Node: prints version requirements and install instructions
- Port conflicts: detects and reports which process is using the port
- Migration failures: prints Alembic error output, does not leave DB in half-migrated state
- Colored output: `GREEN` for success, `RED` for errors, `YELLOW` for warnings, `CYAN` for info

### Validation Contract

1. `./dev setup` is idempotent — running twice produces no errors
2. `./dev up --native` starts and health-checks all 6 services
3. `curl localhost:8000/api/v1/health` returns `{"status":"healthy"}`
4. `curl localhost:5173/` returns the React HTML shell
5. `./dev test` runs backend + frontend tests successfully
6. `./dev down` stops all services, `docker ps` shows no book-quiz containers
7. `.env` values are the only difference from `docker-compose.yml` defaults

## Agent Log

| Date | Agent | Action | Summary |
|------|-------|--------|----------|
| 2026-08-03T01:05:23Z | system | created | Issue filed |
| 2026-08-03T01:35:00Z | architect | plan | Architecture design written to issue file |

## Review Feedback

*No review feedback yet.*

## Implementation Notes

**Engineer**: delegated subagent | **Date**: 2026-08-03

### Blocker resolutions (from architecture review)

- **CR-1** ✅ `docker-compose.yml` created at repo root — services: db (postgres:16-alpine, healthcheck pg_isready), redis (redis:7-alpine, healthcheck redis-cli ping), backend (FastAPI on 8000), celery-worker (celery -A app.worker worker), frontend (nginx on 5173→80). Named volumes `pgdata`/`redisdata`, network `bookquiz-dev`. `.env` interpolation for credentials/ports.
- **CR-2** ✅ `backend/app/worker.py` — Celery app wired to REDIS_URL broker/backend, JSON serialization, task time limits, `include=["app.tasks"]` with ImportError guard until the hydration task module lands. Verified `celery_app` imports, name `bookquiz`, broker `redis://localhost:6379/0`.
- **CR-3** ✅ `backend/alembic.ini` hardcoded URL documented as placeholder; `alembic/env.py` already overrides via `app.core.config.get_settings()` → `DATABASE_URL` env var. Verified resolution.
- **CR-4** ✅ Root `Dockerfile` multi-stage: node build frontend → python runtime backend, bundles `frontend-dist`, non-root user, healthcheck. Supports fly.toml `app` (uvicorn) and `worker` (celery) processes.

### Review recommendations applied

- **R-3** ✅ Modularized: `dev` dispatcher (~90 lines) + `lib/dev-{common,setup,up,down,test,db,util}.sh`.
- **R-4** ✅ Signal trap `trap cleanup_all EXIT INT TERM`; PIDs tracked in `/tmp/book-quiz-dev/*.pid`; cleanup kills tracked processes.
- **R-5** ✅ `dev setup` generates JWT_SECRET_KEY (openssl rand -hex 32) + ADMIN_API_KEY (openssl rand -hex 16) into .env; `dev generate-secrets` re-rotates.
- **R-6** ✅ `.env.example` sets RATE_LIMIT_ENABLED=false; compose file documented as dev stack mirroring production service versions.
- R-8 ✅ RATE_LIMIT_ENABLED=false default.
- R-9 (docs) — WSL2 note is in the doctor output dependency guidance; full platform matrix deferred.

### Command surface

setup, generate-secrets, up [--native|--docker], down [--volumes], test [--unit|--e2e|--coverage], lint, format, db-migrate, db-migrate-new, db-reset, db-seed (stub), logs [svc], ps, shell <svc>, build, clean, doctor, help.

### Verification performed

- `bash -n` syntax check on `dev` + all 7 lib modules: PASS
- `./dev help` exit 0, `./dev` (no args) exit 0
- `./dev doctor` exit 1 (correctly flags missing Docker + .env on this machine)
- `./dev setup` idempotent (2nd run reuses venv/node_modules/.env); exits 1 only at Docker step (machine lacks Docker)
- `./dev up` exits 1 with actionable ".env missing — run ./dev setup" when .env absent
- `./dev down` graceful no-op when nothing running
- `celery_app` import verified; compose YAML validated via PyYAML
- Alembic resolves DATABASE_URL from env (CR-3 verified)

### Decisions needing approval

- **Celery task module**: `app/tasks/` does not exist yet; worker.py guards the import so the worker boots now. Tasks land with hydration beads (book-quiz-jsh/gpr).
- **`dev test --e2e`** requires the stack running (checked via backend health endpoint) — intentional to avoid silent no-op e2e.
- **fly.toml DATABASE_URL/REDIS_URL placeholders** unchanged (secrets set via `fly secrets set`); root Dockerfile now exists so `flyctl deploy` will resolve the build reference.

### Residual risks

- Docker unavailable on the dev machine used for verification — compose startup paths (db health waits, container exec) not exercised live.
- `dev db-seed` is a stub pending hydration pipeline.
- e2e Playwright needs hydrated data to assert non-empty search; known project-wide gap tracked by feature beads.

## Test Results

*Not yet tested.*
# dev CLI — Architecture Plan

**Bead**: `book-quiz-xdm` | **Status**: `status_plan`
**Author**: architect | **Date**: 2026-08-03

## Architecture Plan

### Component Diagram

```
┌─────────────────────────────────────────────────────┐
│                    ./dev script                      │
│  (single bash script at repo root, ~600 lines)      │
├─────────────────────────────────────────────────────┤
│  Command dispatch: setup | up | down | test | ...   │
├─────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Docker   │  │ Python   │  │ Node.js          │  │
│  │ Compose  │  │ venv     │  │ npm              │  │
│  │ (DB/Redis│  │ (backend)│  │ (frontend)       │  │
│  │  Celery) │  │          │  │                  │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Design Decisions

**ADR-dev-001: Bash script over Makefile**
- **Decision**: Single `dev` bash script at repo root
- **Rationale**: More flexible than Makefile (conditionals, colored output, dependency detection). Single file for discoverability. No additional build tools needed — bash is universal on macOS/Linux.

**ADR-dev-002: Dual-mode operation (native vs docker)**
- **Decision**: `dev up` defaults to native mode (backend + frontend run on host, DB + Redis in Docker). `dev up --docker` runs everything in containers.
- **Rationale**: Native mode gives faster iteration (hot reload, no rebuild). Docker mode provides production parity for debugging deployment issues.
- **Native mode**: PostgreSQL + Redis + Celery in Docker. Backend (uvicorn --reload) and frontend (Vite HMR) on host.
- **Docker mode**: All 6 services in Docker Compose, matching `docker-compose.yml` + `fly.toml`.

**ADR-dev-003: `.env` as single source of config truth**
- **Decision**: All service configuration (ports, DB URLs, secrets) flows from `.env`. Production overrides via `fly secrets set`.
- **Rationale**: `.env` is the ONLY documented diff between local and production.

### `dev up` Flow

```
1. Load .env, validate required vars
2. Check dependencies: docker, python3, node
3. Start Docker services (db, redis) via `docker compose up -d`
4. Wait for health checks (pg_isready, redis-cli ping)
5. Run Alembic migrations: `cd backend && alembic upgrade head`
6. [Native] Start Celery worker: `cd backend && celery -A app.worker worker`
7. [Native] Start backend: `cd backend && uvicorn app.main:app --reload`
8. [Native] Start frontend: `cd frontend && vite --host`
9. [Docker] Start all: `docker compose up -d --build`
10. Print service URLs and health status
```

### `dev down` Flow

```
1. [Native] Kill background processes: uvicorn, vite, celery
2. Stop Docker containers: `docker compose down`
3. [--volumes] Remove volumes: `docker compose down -v`
```

### File Structure

```
repo-root/
├── dev                    # ← THE SCRIPT (single file)
├── .env                  # generated by dev setup, gitignored
├── .env.example          # committed template with placeholders
├── docker-compose.yml    # production-mirroring compose file
├── backend/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── requirements.txt
└── frontend/
    ├── Dockerfile
    └── package.json
```

### `.env.example` Design

```bash
# ── Local Development ────────────────────────────
ENVIRONMENT=development
DEBUG=true

# ── Database ─────────────────────────────────────
DATABASE_URL=postgresql://bookquiz:bookquiz_dev@localhost:5432/bookquiz

# ── Redis ────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── Auth (generate with: openssl rand -hex 32) ──
JWT_SECRET_KEY=change-me-in-production

# ── OpenAI (required for question generation) ───
OPENAI_API_KEY=sk-your-key-here

# ── Admin ────────────────────────────────────────
ADMIN_API_KEY=admin-dev-key-change-me

# ── Rate Limiting ────────────────────────────────
RATE_LIMIT_ENABLED=true
```

### Command Reference

| Command | Implementation |
|---------|---------------|
| `setup` | Creates venv (`python3 -m venv`), `npm ci`, copies `.env.example`, `docker compose` volume init, `alembic upgrade head`, `pre-commit install` |
| `up [--native\|--docker]` | Docker Compose for infra, then native or containerized app layer |
| `down [--volumes]` | Kill native processes, `docker compose down` |
| `test [--unit\|--e2e\|--coverage]` | `pytest` + `vitest run` + `playwright test` |
| `lint` | `ruff check` + `mypy` + `eslint` + `prettier --check` |
| `format` | `ruff format` + `prettier --write` |
| `db-migrate` | `cd backend && alembic upgrade head` |
| `db-migrate-new "msg"` | `cd backend && alembic revision --autogenerate -m "msg"` |
| `db-reset` | `docker compose down -v && docker compose up -d db && alembic upgrade head` |
| `db-seed` | Run seed script (stub — requires hydration pipeline) |
| `logs [svc]` | `docker compose logs -f [svc]` + native process logs |
| `ps` | `docker compose ps` + native process status |
| `build` | `docker compose build` |
| `clean` | `docker compose down -v`, remove `.venv`, `node_modules`, `__pycache__`, `dev.db` |
| `doctor` | Check: docker, python3, node, port conflicts, `.env` exists, venv exists |

### Dependencies

- **Docker + Docker Compose v2** — required (provides PostgreSQL + Redis)
- **Python 3.12+** — required for backend
- **Node.js 22+** — required for frontend
- **jq** — optional (for JSON parsing in `dev ps`)

### Error Handling

- Each command validates prerequisites before running
- Missing Docker: prints install URL for the detected OS
- Missing Python/Node: prints version requirements and install instructions
- Port conflicts: detects and reports which process is using the port
- Migration failures: prints Alembic error output, does not leave DB in half-migrated state
- Colored output: `GREEN` for success, `RED` for errors, `YELLOW` for warnings, `CYAN` for info

### Validation Contract

1. `./dev setup` is idempotent — running twice produces no errors
2. `./dev up --native` starts and health-checks all 6 services
3. `curl localhost:8000/api/v1/health` returns `{"status":"healthy"}`
4. `curl localhost:5173/` returns the React HTML shell
5. `./dev test` runs backend + frontend tests successfully
6. `./dev down` stops all services, `docker ps` shows no book-quiz containers
7. `.env` values are the only difference from `docker-compose.yml` defaults
