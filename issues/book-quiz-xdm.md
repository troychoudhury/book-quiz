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

## Review Feedback

*No review feedback yet.*

## Implementation Notes

*Not yet implemented.*

## Test Results

*Not yet tested.*
