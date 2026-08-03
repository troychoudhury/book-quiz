# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:6cd5cc61 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->


## Build & Test

```bash
# Full development environment
make dev               # Start backend + frontend
docker compose up       # Full Docker environment

# Testing
make test              # All tests (backend + frontend)
make test-backend      # pytest with coverage
make test-frontend     # vitest with coverage
make test-e2e          # Playwright E2E tests

# Linting
make lint              # ruff + mypy + eslint + prettier
make format            # Auto-format all code

# Database
make migrate           # Run Alembic migrations

# AI Agent Loop
./ai-agent-loop.sh     # Run full engineering pipeline
./ai-agent-loop.sh --phase 03  # Start from implementation phase
./ai-agent-loop.sh --dry-run    # Preview without changes
```

## Architecture Overview

**Book Quiz** — A web app for readers to search books and take AI-generated
comprehension quizzes.

- **Frontend**: React + TypeScript + Vite (port 5173)
- **Backend**: Python FastAPI (port 8000)
- **Database**: PostgreSQL 16 with GIN trigram search
- **Cache/Queue**: Redis + Celery for background AI jobs
- **Deployment**: Docker → Fly.io via GitHub Actions

See `docs/ARCHITECTURE.md` for full system design.

## Conventions & Patterns

1. **ATDD**: Acceptance tests written BEFORE implementation
2. **OOP Services**: Business logic in `app/services/`, thin API routes
3. **Pydantic v2**: All request/response validation via Pydantic models
4. **Zustand + React Query**: Global state (Zustand) + server state (React Query)
5. **Feature branches**: One branch per bead/issue
6. **Quality gates must pass**: lint → type-check → test → coverage before merge

### Docker Invocation in Dev Scripts (CRITICAL)

**NEVER use raw `docker exec` or `docker compose` in `lib/*.sh`.** Always use the wrappers:
- `docker_run exec ...` (not `docker exec ...`)
- `compose ...` or `compose_run ...` (not `docker compose ...`)

These wrappers (in `lib/dev-common.sh`) handle DOCKER_HOST dead-socket fallback, sudo, and sg. Raw usage bypasses this chain and causes environment-dependent failures. This lesson is captured in beads memory — run `bd remember --list` to review.

A pre-commit hook enforces this. New lib scripts will be rejected on commit if they use raw docker commands.
