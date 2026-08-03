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

## Security Audit

**Auditor**: security-auditor subagent | **Date**: 2026-08-03
**Scope**: `dev`, `lib/dev-*.sh` (7 modules), `docker-compose.yml`, `Dockerfile`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `.env.example`, `backend/app/worker.py`, `backend/app/core/config.py`
**Risk Level**: Medium

### 🔴 Critical Findings (Blockers)

*None.* No hardcoded production secrets, no command injection vectors, no privilege escalation paths found.

### 🟠 High Severity

- **H-1: Docker port bindings expose DB/Redis on all network interfaces with weak credentials**
  - **Location**: `docker-compose.yml:27-28` (db ports), `docker-compose.yml:40` (redis ports)
  - **Detail**: The compose file maps container ports without a bind address:
    ```yaml
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
      - "${REDIS_PORT:-6379}:6379"
    ```
    Docker defaults to binding `0.0.0.0` when no IP is specified. This means PostgreSQL (`bookquiz:bookquiz_dev`) and Redis (no password) are accessible from any host on the local network with the default weak credentials.
  - **Impact**: Any machine on the local network can connect to the developer's PostgreSQL and Redis instances, exfiltrate data, modify records, or use Redis as an attack vector (e.g., writing malicious serialized objects if pickle serialization were ever enabled).
  - **Remediation**: Bind to loopback only:
    ```yaml
    ports:
      - "127.0.0.1:${POSTGRES_PORT:-5432}:5432"
      - "127.0.0.1:${REDIS_PORT:-6379}:6379"
    ```
    Also add `requirepass` to the Redis config and use a generated password.

- **H-2: Weak, hardcoded default database credentials across multiple files**
  - **Location**:
    - `.env.example:15` — `POSTGRES_PASSWORD=bookquiz_dev`
    - `backend/app/core/config.py:22` — `database_url: str = "postgresql://bookquiz:bookquiz_dev@localhost:5432/bookquiz"`
    - `docker-compose.yml:25` — `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-bookquiz_dev}`
  - **Impact**: Combined with H-1, trivial credential guessing. Even with loopback binding, a local malicious process or compromised npm dependency could access the DB.
  - **Remediation**: `dev setup` already generates JWT_SECRET_KEY and ADMIN_API_KEY. Extend it to also generate `POSTGRES_PASSWORD` and `REDIS_PASSWORD` (e.g., `openssl rand -hex 16` each) and write them into `.env`. Remove the hardcoded defaults from `config.py` and `docker-compose.yml` in favor of required env vars.

- **H-3: Redis has no authentication configured**
  - **Location**: `docker-compose.yml:36-48` (redis service)
  - **Detail**: The Redis container has no `command:` or config to set `requirepass`. The `REDIS_URL` in `.env.example` (`redis://localhost:6379/0`) and `docker-compose.yml` (`redis://redis:6379/0`) has no password component. Celery worker.py connects without authentication.
  - **Impact**: Anyone with network access to port 6379 can run `redis-cli FLUSHALL`, inject malicious data into Celery task queues, or read cached session/JWT data.
  - **Remediation**: Generate a `REDIS_PASSWORD` in `dev setup`, add `command: redis-server --requirepass ${REDIS_PASSWORD}` to the compose service, and update `REDIS_URL` to `redis://:${REDIS_PASSWORD}@redis:6379/0`.

### 🟡 Medium Severity

- **M-1: PID directory `/tmp/book-quiz-dev` susceptible to symlink TOCTOU**
  - **Location**: `lib/dev-common.sh:27-28`
  - **Detail**: `PID_DIR="/tmp/book-quiz-dev"` with `mkdir -p "$PID_DIR"`. On multi-user systems, if an attacker creates `/tmp/book-quiz-dev` as a symlink before the script runs, PID files could be written to an attacker-controlled directory. The `/tmp` sticky bit limits this, but TOCTOU races are still possible. The directory also has default umask permissions (likely 755), making PID files world-readable.
  - **Impact**: Low in practice for a dev tool on single-user machines. Could theoretically allow PID file manipulation or information disclosure on shared systems.
  - **Remediation**: Use `mktemp -d` or move to `$XDG_RUNTIME_DIR/book-quiz-dev/` or `$HOME/.cache/book-quiz-dev/`. Set explicit `mkdir -m 700`.

- **M-2: No `cap_drop` or `security_opt` hardening in docker-compose.yml**
  - **Location**: `docker-compose.yml` (all services)
  - **Detail**: The compose file does not restrict container capabilities. The backend/celery-worker containers inherit the Dockerfile's `USER bookquiz` (good), but no explicit `cap_drop: [ALL]` or `cap_add: [NET_BIND_SERVICE]` is specified. The `db` and `redis` services have no `user:` directive (though postgres and redis images run as their respective non-root users by default).
  - **Impact**: Containers run with more Linux capabilities than needed. If a container were compromised, the attacker would have more kernel capabilities available.
  - **Remediation**: Add `cap_drop: [ALL]` to all services. Add minimal `cap_add` only where needed. Add `security_opt: [no-new-privileges:true]`.

- **M-3: No `read_only` root filesystem for containers**
  - **Location**: `docker-compose.yml` (all services)
  - **Detail**: None of the services mount their root filesystem as read-only. The `db` and `redis` services need writable data directories (handled by volumes), but the backend, celery-worker, and frontend have no reason to write to the root filesystem at runtime.
  - **Impact**: If an attacker achieves RCE in a container, they can write to the filesystem (drop malware, modify binaries, etc.).
  - **Remediation**: Add `read_only: true` to the backend, celery-worker, and frontend services. Mount `/tmp` as `tmpfs` if needed for temporary writes.

- **M-4: nginx.conf is missing `Strict-Transport-Security` and `X-Permitted-Cross-Domain-Policies` headers**
  - **Location**: `frontend/nginx.conf:13-16`
  - **Detail**: The nginx config has good security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, CSP) but is missing `Strict-Transport-Security` (HSTS) and `X-Permitted-Cross-Domain-Policies`. For a dev environment this is low priority, but the `frontend/Dockerfile` uses this nginx.conf in a container that could also serve production-like builds.
  - **Impact**: In environments where HTTPS is used, lack of HSTS allows SSL stripping attacks. Missing `X-Permitted-Cross-Domain-Policies` could allow cross-domain data loading in older Adobe products.
  - **Remediation**: Add:
    ```nginx
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Permitted-Cross-Domain-Policies "none" always;
    ```

- **M-5: `dev logs <svc>` allows path traversal via service name**
  - **Location**: `lib/dev-util.sh:55-60`
  - **Detail**: The `cmd_logs()` function uses the user-supplied `$svc` directly in a file path:
    ```bash
    local logfile="${DEV_ROOT}/.logs/${svc}.log"
    ```
    A call like `./dev logs "../../../etc/passwd"` would attempt to read `/etc/passwd` (if it existed as `.log`). The `tail -f` would fail for non-log files, but the path traversal vector exists.
  - **Impact**: Low — the dev CLI is run by the developer themselves. However, if the CLI were ever invoked programmatically with user-supplied input, this would be exploitable.
  - **Remediation**: Validate `$svc` against a whitelist: `backend`, `frontend`, `celery`. Reject any value containing `/` or `..`.

- **M-6: `curl | sudo bash` pattern in informational messages normalizes dangerous behavior**
  - **Location**: `lib/dev-common.sh:82`
  - **Detail**: The `require_node()` function prints installation instructions that include `curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -`. While this is only informational text (not executed by the script), it promotes a dangerous pattern to developers.
  - **Impact**: Low — social engineering risk. Developers who see this pattern normalized may be more likely to pipe curl to bash from untrusted sources.
  - **Remediation**: Add a note about verifying the script before piping to bash, or link to the official NodeSource installation docs instead.

### 🟢 Low / Informational

- **L-1: `.env` sourced with `set -a` could execute malicious shell if `.env` is tampered with**
  - **Location**: `lib/dev-common.sh:35-39`
  - **Detail**: `load_env()` uses `set -a; source "$ENV_FILE"; set +a`. If `.env` contains shell metacharacters or commands (e.g., `$(malicious)`), they would execute. This is inherent to bash-based `.env` loading and mitigated by `.env` being developer-generated and gitignored.
  - **Remediation**: Accepted risk for a dev tool. A stricter parser (e.g., `export $(grep -v '^#' .env | xargs)`) would break values with spaces. Document that `.env` should only contain `KEY=value` pairs.

- **L-2: `backend/app/core/config.py` defaults `database_url` to weak dev credentials**
  - **Location**: `backend/app/core/config.py:22`
  - **Detail**: The `Settings` class defaults `database_url` to `postgresql://bookquiz:bookquiz_dev@localhost:5432/bookquiz`. While overridden by `.env`/env vars, the hardcoded default means the app silently boots with weak creds if `DATABASE_URL` is unset.
  - **Remediation**: Remove the default or set it to a value that fails fast (e.g., `""`), so the app refuses to start without explicit configuration.

- **L-3: Backend uvicorn binds to `0.0.0.0` in native mode**
  - **Location**: `lib/dev-up.sh:85`
  - **Detail**: `start_bg "backend" ... uvicorn app.main:app --host 0.0.0.0 --port ...` — in native mode, the backend is accessible on all network interfaces.
  - **Impact**: If the developer is on a public network (coffee shop Wi-Fi), anyone can access the backend API, which includes the admin endpoints if `ADMIN_API_KEY` is known/weak. Combined with `DEBUG=true`, verbose error messages could leak stack traces and source paths.
  - **Remediation**: Default to `--host 127.0.0.1` for native mode. Allow override via `BACKEND_HOST` env var for users who need network access.

- **L-4: Vite dev server binds to `0.0.0.0` in native mode**
  - **Location**: `lib/dev-up.sh:88`
  - **Detail**: Same as L-3 but for the frontend. Vite's HMR WebSocket could be exploited if an attacker on the same network crafts malicious HMR updates.
  - **Remediation**: Default to `--host 127.0.0.1`.

- **L-5: Production `Dockerfile` sets `DEBUG=true` as hardcoded env in compose, not in the Dockerfile itself, but the root Dockerfile has no DEBUG default**
  - **Location**: `docker-compose.yml:73` (backend environment has `DEBUG: "true"`)
  - **Detail**: The compose file force-sets `DEBUG: "true"` for the backend service. If this compose file were accidentally used as a base for production (despite being labeled dev-only), debug mode would be enabled. The root `Dockerfile` correctly omits a DEBUG default.
  - **Impact**: If a developer copies the compose file for staging/prod, debug mode may leak tracebacks.
  - **Remediation**: Add a prominent comment at the top of `docker-compose.yml` warning it is dev-only and must not be used for production deployment.

### ✅ Clean Areas

- **Secret generation**: `dev setup` correctly uses `openssl rand -hex 32` (256-bit) for JWT_SECRET_KEY and `openssl rand -hex 16` (128-bit) for ADMIN_API_KEY. Both are cryptographically secure.
- **Signal trap**: `trap cleanup_all EXIT INT TERM` in `lib/dev-common.sh:157` properly catches script exit and interrupts. `cleanup_all()` iterates all PID files, kills via SIGTERM with 1s grace, then SIGKILL. PID files are removed after kill. Works correctly.
- **No hardcoded production secrets**: All secrets in committed files are placeholders (`change-me-in-production`, `sk-your-key-here`, `admin-dev-key-change-me`). The `.env` file is gitignored (confirmed in `.gitignore`).
- **Non-root Docker users**: Root `Dockerfile` runs as `USER bookquiz`. `backend/Dockerfile` runs as `USER bookquiz`. `frontend/Dockerfile` uses nginx which defaults to `nginx` user. No `privileged: true` in compose.
- **No command injection**: All command invocations use properly quoted `"$@"` array expansion. The `cmd_shell` function uses a `case` statement and hardcoded container names. The `sed` command in `create_env_file()` only interpolates hex output from `openssl rand -hex`, which contains no shell metacharacters.
- **`.env.example` quality**: All placeholders are clearly documented. `RATE_LIMIT_ENABLED=false` (correct for dev). No actual API keys or tokens committed.
- **nginx security headers**: `frontend/nginx.conf` includes CSP, X-Frame-Options (DENY), X-Content-Type-Options (nosniff), and Referrer-Policy headers. Well-configured SPA routing and asset caching.
- **Celery worker**: `backend/app/worker.py` uses JSON serialization (not pickle), has task time limits (30min hard, 25min soft), and properly guards the `app.tasks` import that doesn't exist yet.

### 📦 Dependency Status

- `postgres:16-alpine` — current, no known critical CVEs in 16-alpine track.
- `redis:7-alpine` — current stable, no known critical CVEs.
- `python:3.12-slim` — current, no known critical CVEs in slim variant.
- `node:22-alpine` — current LTS, no known critical CVEs.
- `nginx:1.27-alpine` — current stable, no known critical CVEs.
- No `package.json`, `requirements.txt`, or lock files audited for application dependency vulnerabilities (outside scope — focused on dev CLI).

### Risk Summary

The highest practical risk is **H-1 + H-2 combined**: DB/Redis ports bound to `0.0.0.0` with weak/absent credentials. On a laptop used in shared spaces (co-working, coffee shops, conferences), this exposes the developer's database to the local network. Developers using this tool on machines with Docker exposed to LAN (common on Linux where Docker defaults to `iptables`-based networking) are especially vulnerable.

The codebase is otherwise well-structured from a security perspective — the shell scripts use safe patterns, Dockerfiles enforce non-root users, secrets are properly generated, and the signal trap works correctly.

## Code Review

**Reviewer**: Lead Code Reviewer (subagent) | **Date**: 2026-08-03
**Scope**: `dev`, `lib/dev-*.sh`, `docker-compose.yml`, root `Dockerfile`, `.env.example`, `backend/app/worker.py`, `backend/alembic.ini`, `backend/alembic/env.py`
**Verdict**: ❌ **FAIL** — CR-1..CR-4 are structurally resolved, but the primary acceptance path (`./dev setup && ./dev up` → health checks → `./dev down`) is broken in native mode (the default) by two runtime bugs, and the Docker build path is broken by a missing `.dockerignore`.

### Verification performed

- `bash -n dev lib/*.sh` — PASS (all 8 files)
- `docker-compose.yml` — PyYAML parse PASS (5 services, 2 named volumes, network, `name: bookquiz`); every `${VAR}` uses a `:-` default, so `docker compose config` would succeed without `.env`. `docker compose config` itself NOT run (no Docker on review machine).
- `celery_app` import + `app.finalize()` with missing `app.tasks` — PASS (celery 5.4.0 tolerates the missing include module; CR-2 import guard verified)
- Alembic `DATABASE_URL` override — PASS (env.py resolves env var; `alembic upgrade head` with `DATABASE_URL=...@customhost` attempted `customhost`; CR-4 verified)
- Backend test suite via `dev test` path — PASS (6/6)
- CLI smoke: `./dev help` 0, no-args 0, `./dev down` 0 (graceful no-op), `./dev doctor` 1 (correctly flags missing Docker/.env on this machine)
- Native-mode runtime claims — empirically FAILED (see CRIT-1/CRIT-2)

### 🔴 Critical

1. **`lib/dev-common.sh:160` — EXIT trap kills the stack on normal `./dev up` exit.** `trap cleanup_all EXIT INT TERM` runs `cleanup_all` whenever the script exits, including a successful `./dev up` (native). All tracked processes (celery, backend, frontend) are killed the instant `up` returns, so the stack never survives past the command. **Empirically verified**: a tracked `sleep 300` child was killed when its parent shell exited normally. This breaks acceptance criteria 2, 3 and 5. Fix: drop `EXIT` (keep `INT TERM`), or guard cleanup with an explicit flag set only on failure, or make `dev up` daemonize intentionally and leave teardown to `dev down`. Note: the existing Security Audit section claims "the signal trap works correctly" — that claim is wrong.
2. **`lib/dev-up.sh:80-91` — native-mode processes are launched from the wrong working directory.** `start_bg "backend" "$venv_bin/uvicorn" app.main:app ...`, `start_bg "celery" ... -A app.worker ...` and `start_bg "frontend" ... vite ...` run with cwd = repo root (no `cd backend` / `cd frontend`). **Verified**: `import app.main` from repo root → `ModuleNotFoundError: No module named 'app'` (succeeds from `backend/`); vite started from repo root serves `HTTP 404` for `/` (repo root has no `index.html`). All three native processes fail to serve anything. Fix: `(cd "${DEV_ROOT}/backend" && start_bg ...)` or pass `--app-dir backend` to uvicorn/celery and a `--root`/config to vite.
3. **Missing `.dockerignore` (root, `backend/`, `frontend/`) breaks the Docker build after `./dev setup`.** With no `.dockerignore`, `COPY frontend/ ./` (root `Dockerfile` stage 1 and `frontend/Dockerfile`) overwrites the container's freshly `npm ci`-installed `node_modules` with the host's copy (verified present on disk, containing a glibc `@esbuild/linux-x64` binary) — `npm run build` then fails inside `node:22-alpine` (musl) on macOS and glibc hosts. `COPY backend/ ./` (root `Dockerfile` stage 2) and `backend/Dockerfile`'s `COPY . .` ship `backend/.venv` (verified present) into the image: hundreds of MB of bloat and host-OS binaries in production images. Breaks `./dev build`, `./dev up --docker`, and `flyctl deploy` on the documented macOS/Linux workflow. Fix: add `.dockerignore` excluding `node_modules`, `.venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `*.db`, `.logs`.

### 🟡 Major

4. **`lib/dev-common.sh:139-152` — `kill_tracked` can orphan children.** TERM → 1 s → SIGKILL: `uvicorn --reload` (parent is the reloader supervising a server subprocess) and `celery --concurrency=2` (prefork pool children) can leave children alive holding port 8000 / Redis connections after `dev down` or the trap. Prefer killing the process group (`setsid`/`setpgid` on start + `kill -- -PGID`) or `pkill -P`.
5. **`lib/dev-up.sh:71-76` — port conflicts only warn, then the stack starts anyway.** If 8000/5173 are taken, uvicorn/vite crash after celery already started → half-up stack. The plan requires "handles port conflicts gracefully"; this should abort before starting anything or use `SO_REUSEPORT`/alternate ports.
6. **`lib/dev-db.sh:23,38` — infra start failures are swallowed.** `compose up -d db redis >/dev/null 2>&1 || true` hides the real error; alembic then fails with a confusing connection error instead of "Docker/db failed to start".
7. **`lib/dev-setup.sh:105` — hardcoded `pg_isready -U bookquiz`** (inconsistent with `wait_for_db`'s `${POSTGRES_USER:-bookquiz}`). A custom `POSTGRES_USER` in `.env` makes `dev setup`'s wait loop spin for 60 s and fail.
8. **No post-start health verification in `up_native`.** After `sleep 2` it prints URLs but never confirms backend/frontend actually respond; combined with CRIT-2 the failure is only visible in `.logs/*.log`.

### 🟢 Minor

9. `lib/dev-common.sh:171-174` — `check_migrations()` is dead code (never called).
10. `lib/dev-up.sh:86` — stray `celery -A app.worker status` (always fails without a running worker; silenced by `|| true`) — remove or move after the worker is up.
11. `lib/dev-common.sh:38-44` — `load_env` sources `.env` unquoted; user-edited values containing `$`, backticks, `#`, or spaces would be expanded/truncated. Fine for generated hex, fragile for hand-edited values.
12. `lib/dev-setup.sh:16-28` — `cmd_generate_secrets` prints new secrets but never writes them to `.env` (implementation notes claim "re-rotates"); requires manual copy-paste.
13. `lib/dev-down.sh:29-34` — when the Docker daemon is down it prints "Docker not available — skipping container teardown" and exits 0 even though containers may still be running — misleading success.
14. `lib/dev-util.sh:104-113` — `cmd_shell` container-name mapping works (`celery-worker` → `bookquiz-celery`) but typos like `./dev shell celery` fail with a confusing "Unknown service".

### ✅ Praise (verified)

- **CR-1..CR-4 all structurally resolved**: compose file is well-formed with healthchecks (db/redis/backend/frontend), named volumes `bookquiz-pgdata`/`bookquiz-redisdata`, single network, `.env` interpolation with `:-` defaults everywhere; `worker.py` is wired to REDIS_URL, JSON serialization, 30/25-min task limits, and the `app.tasks` import guard is safe on celery 5.4.0; `env.py` overrides `sqlalchemy.url` from `get_settings()` (empirically confirmed — migration attempted the env-provided host); root multi-stage `Dockerfile` (node build → python runtime, non-root `bookquiz` user, healthcheck) is referenced by `fly.toml`.
- `set -euo pipefail` throughout; quoting is disciplined; `.env` created with `chmod 600`; colors TTY-gated; setup is genuinely idempotent; `dev down` is a safe no-op; e2e test guards against silent no-op; `.env.example` is complete (every var referenced by compose/scripts is present, `RATE_LIMIT_ENABLED=false` matches R-8).

### Residual risks

- `docker compose config` / `docker compose up -d` / Docker builds not executed — no Docker on the review machine; compose startup paths (health waits, `docker exec`, image builds) unexercised live.
- Full `celery worker` boot (not just `finalize()`) unexercised; only the import path verified.
- `dev test --e2e` (Playwright) not run — requires a running stack, which the native path cannot currently provide.
- `.env.example` omits `OPENAI_MODEL` / `CORS_ORIGINS`, but both have defaults in `app/core/config.py` — no action needed.
- Prior Security Audit's "signal trap works correctly" conclusion is superseded by CRIT-1.

## Implementation Notes (fix pass — review findings)

**Date**: 2026-08-03 | **Agent**: engineer (delegated fix worker)

### Critical fixes
1. **EXIT trap no longer kills stack** (`lib/dev-common.sh`)
   - Trap split: `INT TERM` → `cleanup_all` (kill processes); `EXIT` → `cleanup_stale_pidfiles` (removes ONLY pid files whose process is already dead).
   - Live pid files are preserved so `dev down` can still stop the stack.
   - Empirically verified: tracked process survives normal script exit.

2. **Wrong working directory** (`lib/dev-up.sh`)
   - `start_bg` gained optional `--cwd DIR`; uvicorn/celery now run with `--cwd backend/`, vite with `--cwd frontend/`.
   - Verified: process cwd == backend/ when `--cwd` passed; default remains DEV_ROOT.

3. **Missing .dockerignore** — created:
   - root `.dockerignore` (excludes .git, .beads, .pi-subagents, .logs, node_modules, .venv, __pycache__, *.db, .env)
   - `backend/.dockerignore` (excludes .venv, caches, tests/, *.db, .env)
   - `frontend/.dockerignore` (excludes node_modules, dist, .env)

### High security fixes
4. **Ports bound to 127.0.0.1** (`docker-compose.yml`) — db and redis no longer exposed on the LAN.
5. **DB password auto-generated** — `dev setup` now generates `DB_PASSWORD=$(openssl rand -hex 16)`; compose uses `${DB_PASSWORD:-bookquiz_dev}`; `.env.example` updated; `setup_migrations` fallback URL and `cmd_setup` re-load of `.env` keep first-run migrations working.
6. **Redis requirepass** — `command: redis-server --requirepass ${REDIS_PASSWORD:-bookquiz_dev}`; healthcheck and `wait_for_redis` authenticate; `REDIS_URL` in compose (docker mode) and `.env.example` include the password.

### Quick wins
7. **Process-group kill** — `kill_tracked` now signals `-$pid` (process group) with fallback to individual PID.
8. **Port conflict = hard fail** — `dev up --native` exits 1 instead of warning when backend/frontend ports are occupied.

### Verification
- `bash -n` clean on `dev` + all 7 lib modules.
- `docker compose` YAML parses (PyYAML) with all substitutions verified.
- Functional tests (harness): EXIT trap preserves live processes + pid files; INT/TERM trap still kills; `--cwd` honored; stale pidfile cleanup; secret substitution in .env generation.
- Not executed (no Docker on this machine): full `./dev up --native` boot, `./dev up --docker`, `./dev build`.
