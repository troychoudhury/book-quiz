#!/usr/bin/env bash
#==============================================================================
# dev-setup.sh — `dev setup` and `dev generate-secrets`
#==============================================================================
# Idempotent first-time setup: venv, npm deps, .env (with generated
# secrets), pre-commit hooks, Docker volume init, database migrations.
#==============================================================================

cmd_generate_secrets() {
    require_openssl
    local jwt admin
    jwt="$(openssl rand -hex 32)"
    admin="$(openssl rand -hex 16)"
    ok "Generated secrets:"
    echo "  JWT_SECRET_KEY=${jwt}"
    echo "  ADMIN_API_KEY=${admin}"
    echo ""
    info "To apply: set these in ${ENV_FILE} (or run ./dev setup on a fresh .env)"
}

create_env_file() {
    if [[ -f "$ENV_FILE" ]]; then
        ok ".env already exists — leaving it unchanged."
        return 0
    fi
    if [[ ! -f "${DEV_ROOT}/.env.example" ]]; then
        err ".env.example is missing; cannot create .env."
        exit 1
    fi
    require_openssl
    info "Creating .env from .env.example with generated secrets..."
    # Substitute real secrets so `dev up` boots with unique credentials.
    sed -e "s/^JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$(openssl rand -hex 32)/" \
        -e "s/^ADMIN_API_KEY=.*/ADMIN_API_KEY=$(openssl rand -hex 16)/" \
        "${DEV_ROOT}/.env.example" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ok ".env created with generated secrets."
}

setup_backend() {
    require_python
    step "Backend: Python venv + dependencies"
    if [[ ! -d "${DEV_ROOT}/backend/.venv" ]]; then
        info "Creating Python venv..."
        python3 -m venv "${DEV_ROOT}/backend/.venv"
    else
        ok "venv already exists."
    fi

    local pip="${DEV_ROOT}/backend/.venv/bin/pip"
    if [[ ! -x "$pip" ]]; then
        err "pip not found in venv; recreate with: rm -rf backend/.venv && ./dev setup"
        exit 1
    fi

    info "Installing backend dependencies (this may take a while)..."
    "$pip" install --quiet --upgrade pip
    "$pip" install --quiet -r "${DEV_ROOT}/backend/requirements.txt" -r "${DEV_ROOT}/backend/requirements-dev.txt"
    ok "Backend dependencies installed."
}

setup_frontend() {
    require_node
    step "Frontend: npm dependencies"
    if [[ -d "${DEV_ROOT}/frontend/node_modules" ]]; then
        ok "node_modules already present — running npm ci to sync lockfile."
        (cd "${DEV_ROOT}/frontend" && npm ci --silent)
    else
        info "Installing frontend dependencies..."
        (cd "${DEV_ROOT}/frontend" && npm ci --silent)
    fi
    ok "Frontend dependencies installed."
}

setup_precommit() {
    step "Pre-commit hooks"
    if command_exists pre-commit && [[ -f "${DEV_ROOT}/.pre-commit-config.yaml" ]]; then
        (cd "$DEV_ROOT" && pre-commit install >/dev/null 2>&1) && ok "pre-commit hooks installed."
    elif [[ -f "${DEV_ROOT}/.pre-commit-config.yaml" ]]; then
        warn "pre-commit not installed — skipping hook install (optional)."
    else
        info "No .pre-commit-config.yaml — skipping."
    fi
}

setup_docker_volumes() {
    step "Docker volumes"
    require_docker
    # `docker compose config` validates the file; up -d infra is handled
    # by `dev up`. Creating volumes explicitly makes setup idempotent.
    docker volume create bookquiz-pgdata >/dev/null 2>&1 || true
    docker volume create bookquiz-redisdata >/dev/null 2>&1 || true
    ok "Docker volumes ready (bookquiz-pgdata, bookquiz-redisdata)."
}

setup_migrations() {
    step "Database migrations"
    # Migrations need the DB up; `dev setup` brings infra up briefly.
    require_docker
    if ! docker ps --format '{{.Names}}' | grep -q '^bookquiz-db$'; then
        info "Starting database container for migrations..."
        compose up -d db redis
        # Wait for healthy postgres (max ~60s)
        local attempts=0
        until docker exec bookquiz-db pg_isready -U bookquiz >/dev/null 2>&1; do
            attempts=$((attempts + 1))
            if [[ $attempts -ge 30 ]]; then
                err "Database did not become ready in time."
                exit 1
            fi
            sleep 2
        done
        ok "Database is ready."
    fi

    local alembic_bin="${DEV_ROOT}/backend/.venv/bin/alembic"
    if [[ -x "$alembic_bin" ]]; then
        (cd "${DEV_ROOT}/backend" && DATABASE_URL="${DATABASE_URL:-postgresql://bookquiz:bookquiz_dev@localhost:5432/bookquiz}" "$alembic_bin" upgrade head)
        ok "Migrations applied."
    else
        warn "alembic not installed in venv — skipping migrations (run ./dev up to apply)."
    fi
}

cmd_setup() {
    info "Book Quiz — dev setup (idempotent)"
    load_env
    create_env_file
    setup_backend
    setup_frontend
    setup_precommit
    setup_docker_volumes
    setup_migrations
    echo ""
    ok "Setup complete! Next steps:"
    echo "  ./dev up              # start the full stack"
    echo "  ./dev doctor          # verify the environment"
    echo "  ./dev test            # run the test suite"
}
