#!/usr/bin/env bash
#==============================================================================
# dev-common.sh — shared helpers for the dev CLI
#==============================================================================
# Colors, logging, env loading, dependency checks, and PID management.
# Sourced by the `dev` dispatcher; also usable by individual lib modules.
#==============================================================================

# ── Colors ──────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    C_RED='\033[0;31m'; C_GREEN='\033[0;32m'; C_YELLOW='\033[1;33m'
    C_BLUE='\033[0;34m'; C_CYAN='\033[0;36m'; C_BOLD='\033[1m'; C_NC='\033[0m'
else
    C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_CYAN=''; C_BOLD=''; C_NC=''
fi

info()  { echo -e "${C_BLUE}[dev]${C_NC}  $*"; }
ok()    { echo -e "${C_GREEN}[ok]${C_NC}   $*"; }
warn()  { echo -e "${C_YELLOW}[warn]${C_NC} $*"; }
err()   { echo -e "${C_RED}[err]${C_NC}  $*" >&2; }
step()  { echo -e "${C_CYAN}──${C_NC} $*"; }

# ── Paths ───────────────────────────────────────────────────────────
# SCRIPT_DIR is exported by the `dev` dispatcher before sourcing.
DEV_ROOT="${SCRIPT_DIR:?SCRIPT_DIR must be set by the dispatcher}"
ENV_FILE="${DEV_ROOT}/.env"
PID_DIR="/tmp/book-quiz-dev"
mkdir -p "$PID_DIR"

# ── Env loading ─────────────────────────────────────────────────────
# Load .env if present (never fail when absent — commands validate
# individually). Values with spaces or special chars are handled by
# `set -a` + source; export so child processes (uvicorn, vite) see them.
load_env() {
    if [[ -f "$ENV_FILE" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$ENV_FILE"
        set +a
    fi
}

require_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        err "No .env file found. Run: ./dev setup"
        exit 1
    fi
    load_env
}

# ── Dependency checks ───────────────────────────────────────────────
command_exists() { command -v "$1" >/dev/null 2>&1; }

require_docker() {
    if ! command_exists docker; then
        err "Docker is required but not installed."
        case "$(uname -s)" in
            Darwin)  echo "  Install: https://docs.docker.com/desktop/setup/install/mac-install/" >&2 ;;
            Linux)   echo "  Install: https://docs.docker.com/engine/install/" >&2 ;;
        esac
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        err "Docker daemon is not running. Start Docker Desktop / dockerd and retry."
        exit 1
    fi
}

require_python() {
    if ! command_exists python3; then
        err "Python 3.12+ is required but not installed."
        echo "  macOS: brew install python@3.12" >&2
        echo "  Ubuntu: sudo apt-get install python3.12 python3.12-venv" >&2
        exit 1
    fi
}

require_node() {
    if ! command_exists node; then
        err "Node.js 22+ is required but not installed."
        echo "  macOS: brew install node@22" >&2
        echo "  Ubuntu: curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs" >&2
        exit 1
    fi
}

require_openssl() {
    if ! command_exists openssl; then
        err "openssl is required (used to generate secrets)."
        echo "  macOS: ships with system (LibreSSL is fine). Ubuntu: sudo apt-get install openssl" >&2
        exit 1
    fi
}

# ── Port checks ─────────────────────────────────────────────────────
# Returns 0 when the port is free, 1 when in use (prints the offender).
port_free() {
    local port="$1"
    if command_exists lsof; then
        local offender
        offender="$(lsof -ti "tcp:${port}" 2>/dev/null | head -1 || true)"
        if [[ -n "$offender" ]]; then
            local proc
            proc="$(ps -p "$offender" -o comm= 2>/dev/null || echo "pid $offender")"
            warn "Port $port is in use by: $proc (pid $offender)"
            return 1
        fi
    elif command_exists ss; then
        if ss -tln | grep -q ":${port} "; then
            warn "Port $port is already in use."
            return 1
        fi
    fi
    return 0
}

# ── PID management ──────────────────────────────────────────────────
# Background processes started by `dev up --native` are tracked in
# $PID_DIR so `dev down` and the EXIT trap can kill them reliably.
start_bg() {
    local name="$1"; shift
    local logfile="${DEV_ROOT}/.logs/${name}.log"
    mkdir -p "$(dirname "$logfile")"
    info "Starting $name → ${logfile}"
    # shellcheck disable=SC2068
    nohup "$@" >"$logfile" 2>&1 &
    echo $! > "${PID_DIR}/${name}.pid"
}

kill_tracked() {
    local name="$1"
    local pidfile="${PID_DIR}/${name}.pid"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
            info "Stopping $name (pid $pid)"
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pidfile"
    fi
}

cleanup_all() {
    local any=false
    for pidfile in "${PID_DIR}"/*.pid; do
        [[ -e "$pidfile" ]] || continue
        any=true
        local name
        name="$(basename "$pidfile" .pid)"
        kill_tracked "$name"
    done
    [[ "$any" == true ]] && info "Background processes cleaned up."
    return 0
}

# Trap: always clean up tracked background processes on exit/interrupt.
trap cleanup_all EXIT INT TERM

# ── Misc helpers ────────────────────────────────────────────────────
compose() {
    docker compose -f "${DEV_ROOT}/docker-compose.yml" "$@"
}

confirm() {
    local prompt="$1"
    read -r -p "$prompt [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

check_migrations() {
    if ! command_exists alembic && [[ ! -x "${DEV_ROOT}/backend/.venv/bin/alembic" ]]; then
        return 1
    fi
    return 0
}
