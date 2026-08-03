#!/usr/bin/env bash
#==============================================================================
# dev-db.sh — database operations
#==============================================================================
# db-migrate, db-migrate-new, db-reset, db-seed
#==============================================================================

alembic_run() {
    local venv_bin="${DEV_ROOT}/backend/.venv/bin"
    if [[ ! -x "$venv_bin/alembic" ]]; then
        err "alembic not found in backend/.venv — run ./dev setup first."
        exit 1
    fi
    (cd "${DEV_ROOT}/backend" && "$venv_bin/alembic" "$@")
}

cmd_db_migrate() {
    require_env_file
    require_docker
    # Ensure infra is up so the migration has somewhere to run.
    compose up -d db redis >/dev/null 2>&1 || true
    info "Applying migrations..."
    alembic_run upgrade head
    ok "Migrations applied."
}

cmd_db_migrate_new() {
    local msg="${1:-}"
    if [[ -z "$msg" ]]; then
        err "Usage: ./dev db-migrate-new \"migration message\""
        exit 1
    fi
    require_env_file
    require_docker
    compose up -d db redis >/dev/null 2>&1 || true
    info "Generating migration: $msg"
    alembic_run revision --autogenerate -m "$msg"
    ok "Migration generated. Review it, then: ./dev db-migrate"
}

cmd_db_reset() {
    require_env_file
    require_docker
    if ! confirm "This DESTROYS all local database data. Continue?"; then
        info "Aborted."
        return 0
    fi
    info "Resetting database..."
    compose down -v
    compose up -d db redis
    info "Waiting for database..."
    local attempts=0
    until docker_run exec bookquiz-db pg_isready -U "${POSTGRES_USER:-bookquiz}" >/dev/null 2>&1; do
        attempts=$((attempts + 1))
        if [[ $attempts -ge 30 ]]; then
            err "Database not ready after 60s."
            exit 1
        fi
        sleep 2
    done
    alembic_run upgrade head
    ok "Database reset and migrated."
}

cmd_db_seed() {
    require_env_file
    require_docker
    info "Seeding database..."
    # Stub: the hydration pipeline (book-quiz-jsh / book-quiz-gpr) will
    # populate real data. Until then, seed nothing and report clearly.
    warn "Seeding is not yet implemented — requires the data hydration pipeline."
    warn "Tracked by beads: book-quiz-jsh (hydration) and book-quiz-gpr (question generation)."
}
