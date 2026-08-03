#!/usr/bin/env bash
#==============================================================================
# dev-down.sh — `dev down`
#==============================================================================
# Stops background processes and Docker containers. Volumes are preserved
# by default so data survives; `--volumes` also wipes the database/cache.
#==============================================================================

cmd_down() {
    local with_volumes=false
    case "${1:-}" in
        --volumes) with_volumes=true ;;
        --help|-h) echo "Usage: ./dev down [--volumes]"; return 0 ;;
        "") ;;
        *) err "Unknown flag: $1 (use --volumes to wipe data)"; exit 1 ;;
    esac

    info "Tearing down Book Quiz stack..."

    # 1. Kill tracked native background processes (backend, frontend, celery).
    cleanup_all

    # 2. Stop Docker containers (idempotent — safe when nothing is running).
    if command_exists docker && docker info >/dev/null 2>&1; then
        if [[ "$with_volumes" == true ]]; then
            info "Stopping containers and removing volumes (data will be lost)..."
            compose down -v 2>/dev/null || docker compose down -v 2>/dev/null || true
        else
            info "Stopping containers (volumes preserved)..."
            compose down 2>/dev/null || docker compose down 2>/dev/null || true
        fi
    else
        warn "Docker not available — skipping container teardown."
    fi

    ok "Stack is down."
    if [[ "$with_volumes" == true ]]; then
        info "Volumes removed. Next ./dev up will start with a fresh database."
    else
        info "Data preserved. Run ./dev down --volumes to wipe it."
    fi
}
