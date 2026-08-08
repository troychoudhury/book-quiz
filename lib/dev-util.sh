#!/usr/bin/env bash
#==============================================================================
# dev-util.sh — lint, format, logs, ps, shell, build, clean, doctor, help
#==============================================================================

# ── lint ────────────────────────────────────────────────────────────
cmd_lint() {
    load_env
    local failed=false

    step "Backend lint (ruff + mypy)"
    local venv_bin="${DEV_ROOT}/backend/.venv/bin"
    if [[ -x "$venv_bin/ruff" ]]; then
        (cd "${DEV_ROOT}/backend" && "$venv_bin/ruff" check app/ tests/) || failed=true
        (cd "${DEV_ROOT}/backend" && "$venv_bin/ruff" format --check app/ tests/) || { warn "ruff format issues — run ./dev format"; }
        (cd "${DEV_ROOT}/backend" && "$venv_bin/mypy" app/ --ignore-missing-imports) || failed=true
    else
        warn "ruff/mypy not installed — run ./dev setup."
        failed=true
    fi

    step "Frontend lint (eslint + prettier)"
    if [[ -d "${DEV_ROOT}/frontend/node_modules" ]]; then
        (cd "${DEV_ROOT}/frontend" && npx eslint . --ext .ts,.tsx --max-warnings 0) || failed=true
        (cd "${DEV_ROOT}/frontend" && npx prettier --check .) || { warn "prettier issues — run ./dev format"; }
    else
        warn "frontend deps missing — run ./dev setup."
        failed=true
    fi

    if [[ "$failed" == true ]]; then
        err "Lint found issues (see above)."
        exit 1
    fi
    ok "Lint clean."
}

# ── format ──────────────────────────────────────────────────────────
cmd_format() {
    local venv_bin="${DEV_ROOT}/backend/.venv/bin"
    if [[ -x "$venv_bin/ruff" ]]; then
        step "Formatting backend (ruff)"
        (cd "${DEV_ROOT}/backend" && "$venv_bin/ruff" format app/ tests/)
    fi
    if [[ -d "${DEV_ROOT}/frontend/node_modules" ]]; then
        step "Formatting frontend (prettier)"
        (cd "${DEV_ROOT}/frontend" && npx prettier --write .)
    fi
    ok "Formatting complete."
}

# ── logs ────────────────────────────────────────────────────────────
cmd_logs() {
    local svc="${1:-}"
    if [[ -n "$svc" ]]; then
        # Native-mode process logs live in .logs/<name>.log
        local logfile="${DEV_ROOT}/.logs/${svc}.log"
        if [[ -f "$logfile" ]]; then
            tail -f "$logfile"
            return 0
        fi
        # Otherwise try container logs via the compose helper
        if command_exists docker && docker info >/dev/null 2>&1; then
            compose logs -f "$svc"
            return 0
        fi
        err "No log source for '$svc'."
        exit 1
    fi
    if [[ -d "${DEV_ROOT}/.logs" ]]; then
        info "Native process logs:"
        ls -1 "${DEV_ROOT}/.logs/"
    fi
    if command_exists docker && docker info >/dev/null 2>&1; then
        echo ""
        info "Container logs (compose logs -f <svc>):"
        compose ps --format '{{.Name}}' 2>/dev/null | sed 's/^/  /'
    fi
}

# ── ps ──────────────────────────────────────────────────────────────
cmd_ps() {
    info "Native processes:"
    local any=false
    for pidfile in "${PID_DIR}"/*.pid; do
        [[ -e "$pidfile" ]] || continue
        any=true
        local name pid
        name="$(basename "$pidfile" .pid)"
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
            ok "  $name (pid $pid) — running"
        else
            warn "  $name (pid $pid) — not running"
        fi
    done
    [[ "$any" == false ]] && echo "  (none)"

    if command_exists docker && docker info >/dev/null 2>&1; then
        echo ""
        info "Containers:"
        compose ps 2>/dev/null || compose_run ps 2>/dev/null || true
    fi
}

# ── shell ───────────────────────────────────────────────────────────
cmd_shell() {
    local svc="${1:-}"
    if [[ -z "$svc" ]]; then
        err "Usage: ./dev shell <service> (e.g. backend, db, redis)"
        exit 1
    fi
    require_docker
    case "$svc" in
        db)     docker_run exec -it bookquiz-db psql -U "${POSTGRES_USER:-bookquiz}" "${POSTGRES_DB:-bookquiz}" ;;
        redis)  docker_run exec -it bookquiz-redis redis-cli ;;
        backend|frontend|celery-worker)
            local cname="bookquiz-${svc%-*}"
            docker_run exec -it "$cname" /bin/sh ;;
        *)      err "Unknown service: $svc"; exit 1 ;;
    esac
}

# ── build ───────────────────────────────────────────────────────────
cmd_build() {
    local target="all"
    for arg in "$@"; do
        case "$arg" in
            --help|-h)
                echo "Usage: ./dev build [all|backend|frontend]"
                echo ""
                echo "Build production Docker images."
                echo ""
                echo "  dev build          Build all images (default)"
                echo "  dev build backend  Build backend image (Dockerfile.cloudrun)"
                echo "  dev build frontend Build frontend image (frontend/Dockerfile)"
                return 0
                ;;
            all|backend|frontend) target="$arg" ;;
            *) err "Unknown flag: $arg"; exit 1 ;;
        esac
    done

    require_docker

    if [[ "$target" == "all" || "$target" == "backend" ]]; then
        step "Building backend production image (Dockerfile.cloudrun)"
        docker buildx build --load -f "${DEV_ROOT}/Dockerfile.cloudrun" -t book-quiz-api:latest "${DEV_ROOT}" || {
            err "Backend build failed."
            exit 1
        }
        ok "Backend image built: book-quiz-api:latest"
    fi

    if [[ "$target" == "all" || "$target" == "frontend" ]]; then
        step "Building frontend production image (frontend/Dockerfile)"
        docker buildx build --load -f "${DEV_ROOT}/frontend/Dockerfile" -t book-quiz-frontend:latest "${DEV_ROOT}/frontend" || {
            err "Frontend build failed."
            exit 1
        }
        ok "Frontend image built: book-quiz-frontend:latest"
    fi

    ok "Build complete."
}

# ── clean ───────────────────────────────────────────────────────────
cmd_clean() {
    if ! confirm "This removes containers, volumes, .venv, node_modules, and build artifacts. Continue?"; then
        info "Aborted."
        return 0
    fi
    info "Cleaning everything..."
    cleanup_all
    if command_exists docker && docker info >/dev/null 2>&1; then
        compose down -v 2>/dev/null || true
    fi
    rm -rf "${DEV_ROOT}/backend/.venv"
    rm -rf "${DEV_ROOT}/frontend/node_modules"
    rm -rf "${DEV_ROOT}/frontend/dist"
    rm -rf "${DEV_ROOT}/backend/.pytest_cache" "${DEV_ROOT}/backend/.mypy_cache" "${DEV_ROOT}/backend/.ruff_cache"
    find "${DEV_ROOT}" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    rm -rf "${DEV_ROOT}/.logs"
    rm -f "${DEV_ROOT}/backend/dev.db" "${DEV_ROOT}/backend/test_acceptance.db"
    ok "Clean complete. Run ./dev setup to rebuild."
}

# ── doctor ──────────────────────────────────────────────────────────
cmd_doctor() {
    info "Book Quiz environment doctor"
    local ok_count=0 issue_count=0

    echo ""
    echo -e "${C_BOLD}Dependencies:${C_NC}"
    for dep in docker python3 node openssl; do
        if command_exists "$dep"; then
            ok "  $dep: $(command -v "$dep")"
            ok_count=$((ok_count + 1))
        else
            err "  $dep: MISSING"
            issue_count=$((issue_count + 1))
        fi
    done

    echo ""
    echo -e "${C_BOLD}Docker daemon:${C_NC}"
    if command_exists docker && docker info >/dev/null 2>&1; then
        ok "  Docker daemon running."
        ok_count=$((ok_count + 1))
    else
        err "  Docker daemon not running."
        issue_count=$((issue_count + 1))
    fi

    echo ""
    echo -e "${C_BOLD}Environment:${C_NC}"
    if [[ -f "$ENV_FILE" ]]; then
        ok "  .env exists."
        ok_count=$((ok_count + 1))
        load_env
        [[ -n "${JWT_SECRET_KEY:-}" && "${JWT_SECRET_KEY}" != "change-me-in-production" ]] \
            && ok "  JWT_SECRET_KEY set (generated)." \
            || warn "  JWT_SECRET_KEY is placeholder — run ./dev setup to regenerate."
    else
        err "  .env missing — run ./dev setup."
        issue_count=$((issue_count + 1))
    fi

    echo ""
    echo -e "${C_BOLD}Backend:${C_NC}"
    if [[ -d "${DEV_ROOT}/backend/.venv" ]]; then
        ok "  venv exists."
        ok_count=$((ok_count + 1))
    else
        err "  venv missing — run ./dev setup."
        issue_count=$((issue_count + 1))
    fi

    echo ""
    echo -e "${C_BOLD}Frontend:${C_NC}"
    if [[ -d "${DEV_ROOT}/frontend/node_modules" ]]; then
        ok "  node_modules exists."
        ok_count=$((ok_count + 1))
    else
        err "  node_modules missing — run ./dev setup."
        issue_count=$((issue_count + 1))
    fi

    echo ""
    echo -e "${C_BOLD}Ports:${C_NC}"
    for p in "${BACKEND_PORT:-8000}" "${FRONTEND_PORT:-5173}" "${POSTGRES_PORT:-5432}" "${REDIS_PORT:-6379}"; do
        if port_free "$p"; then
            ok "  port $p free."
            ok_count=$((ok_count + 1))
        else
            issue_count=$((issue_count + 1))
        fi
    done

    echo ""
    if [[ $issue_count -eq 0 ]]; then
        ok "All checks passed ($ok_count checks OK). Ready to ./dev up."
    else
        warn "$issue_count issue(s) found. Run ./dev setup to fix most of them."
        exit 1
    fi
}

# ── help ────────────────────────────────────────────────────────────
cmd_help() {
    cat <<'EOF'
Book Quiz — dev tooling

Usage: ./dev <command> [options]

Environment setup:
  setup              First-time setup (venv, npm, .env, migrations) — idempotent
  generate-secrets   Print new JWT_SECRET_KEY / ADMIN_API_KEY values
  doctor             Diagnose environment issues (deps, ports, .env)

Stack lifecycle:
  up [--native|--docker]  Start full stack (default native: DB/Redis in
                          Docker, apps on host; --docker: everything in containers)
  down [--volumes]        Stop everything (--volumes wipes database data)

Testing & quality:
  test [all|backend|frontend] [--unit|--e2e|--coverage]
                       Run the test suite
  lint                 Run all linters (ruff, mypy, eslint, prettier)
  format               Auto-format all code

Database:
  db-migrate           Apply Alembic migrations
  db-migrate-new "msg" Generate a new migration
  db-reset             Drop + recreate database (with confirmation)
  db-seed              Seed sample data (needs hydration pipeline)

Build & deploy:
  build [all|backend|frontend]
                       Build production Docker images
  deploy [all|backend|frontend|worker] [--staging]
                       Deploy to Cloud Run / Firebase Hosting

Operations:
  logs [service]       Tail logs (backend|frontend|celery or containers)
  ps                   Show process + container status
  shell <service>      Open a shell (db|redis|backend|frontend)
  clean                Remove containers, volumes, venv, node_modules

Other:
  help                 Show this help
EOF
}
