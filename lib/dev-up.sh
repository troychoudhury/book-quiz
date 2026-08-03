#!/usr/bin/env bash
#==============================================================================
# dev-up.sh — `dev up` (native + docker modes)
#==============================================================================
# Native mode (default): PostgreSQL + Redis run in Docker; backend, Celery
# and frontend run as host processes for fast iteration (hot reload).
# Docker mode: everything runs in docker compose for production parity.
#==============================================================================

wait_for_db() {
    info "Waiting for database to be healthy..."
    local attempts=0
    until docker exec bookquiz-db pg_isready -U "${POSTGRES_USER:-bookquiz}" -d "${POSTGRES_DB:-bookquiz}" >/dev/null 2>&1; do
        attempts=$((attempts + 1))
        if [[ $attempts -ge 30 ]]; then
            err "Database not ready after 60s. Check: docker compose ps"
            exit 1
        fi
        sleep 2
    done
    ok "Database healthy."
}

wait_for_redis() {
    info "Waiting for redis to be healthy..."
    local attempts=0
    until docker exec bookquiz-redis redis-cli --no-auth-warning -a "${REDIS_PASSWORD:-bookquiz_dev}" ping 2>/dev/null | grep -q PONG; do
        attempts=$((attempts + 1))
        if [[ $attempts -ge 20 ]]; then
            err "Redis not ready after 40s. Check: docker compose ps"
            exit 1
        fi
        sleep 2
    done
    ok "Redis healthy."
}

run_migrations() {
    local alembic_bin="${DEV_ROOT}/backend/.venv/bin/alembic"
    if [[ ! -x "$alembic_bin" ]]; then
        err "alembic not found in backend/.venv — run ./dev setup first."
        exit 1
    fi
    info "Applying database migrations..."
    (cd "${DEV_ROOT}/backend" && "$alembic_bin" upgrade head)
    ok "Migrations applied."
}

start_infra() {
    step "Starting infrastructure (PostgreSQL + Redis)"
    require_docker
    compose up -d db redis
    wait_for_db
    wait_for_redis
}

up_native() {
    info "Starting stack in NATIVE mode (DB/Redis in Docker, apps on host)"
    require_env_file
    require_docker
    require_python
    require_node

    if [[ ! -d "${DEV_ROOT}/backend/.venv" ]]; then
        err "Backend venv missing — run ./dev setup first."
        exit 1
    fi
    if [[ ! -d "${DEV_ROOT}/frontend/node_modules" ]]; then
        err "Frontend deps missing — run ./dev setup first."
        exit 1
    fi

    start_infra
    run_migrations

    # Port conflict pre-checks — fail fast so we don't leave a half-up stack.
    for p in "${BACKEND_PORT:-8000}" "${FRONTEND_PORT:-5173}"; do
        if ! port_free "$p"; then
            err "Port $p is in use. Free it, or override with BACKEND_PORT/FRONTEND_PORT in .env."
            exit 1
        fi
    done

    step "Starting Celery worker"
    local venv_bin="${DEV_ROOT}/backend/.venv/bin"
    start_bg "celery" --cwd "${DEV_ROOT}/backend" "$venv_bin/celery" -A app.worker worker --loglevel=info --concurrency=2

    step "Starting backend (uvicorn --reload)"
    start_bg "backend" --cwd "${DEV_ROOT}/backend" "$venv_bin/uvicorn" app.main:app --host 0.0.0.0 --port "${BACKEND_PORT:-8000}" --reload

    step "Starting frontend (vite dev server)"
    start_bg "frontend" --cwd "${DEV_ROOT}/frontend" "${DEV_ROOT}/frontend/node_modules/.bin/vite" --host 0.0.0.0 --port "${FRONTEND_PORT:-5173}"

    sleep 2
    echo ""
    ok "Stack is starting up:"
    echo "  Backend:  http://localhost:${BACKEND_PORT:-8000}/api/v1/health"
    echo "  Frontend: http://localhost:${FRONTEND_PORT:-5173}/"
    echo "  Logs:     ./dev logs [backend|frontend|celery]"
    echo ""
    info "Run ./dev down to stop."
}

up_docker() {
    info "Starting stack in DOCKER mode (all services in containers)"
    require_env_file
    require_docker
    compose up -d --build
    echo ""
    ok "Stack is starting:"
    echo "  Backend:  http://localhost:${BACKEND_PORT:-8000}/api/v1/health"
    echo "  Frontend: http://localhost:${FRONTEND_PORT:-5173}/"
    echo ""
    info "Run ./dev down to stop."
}

cmd_up() {
    local mode="native"
    case "${1:-}" in
        --native) mode="native" ;;
        --docker) mode="docker" ;;
        --help|-h) echo "Usage: ./dev up [--native|--docker]"; return 0 ;;
        "") ;;
        *) err "Unknown flag: $1 (use --native or --docker)"; exit 1 ;;
    esac

    if [[ "$mode" == "native" ]]; then
        up_native
    else
        up_docker
    fi
}
