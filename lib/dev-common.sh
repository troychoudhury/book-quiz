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

# ── OS detection ────────────────────────────────────────────────────
os_id() {
    local id
    id="$(uname -s)"
    case "$id" in
        Darwin) echo "macos" ;;
        Linux)
            if [[ -f /etc/os-release ]]; then
                # shellcheck disable=SC1091
                source /etc/os-release
                echo "${ID}"
            else
                echo "linux"
            fi
            ;;
        *) echo "unknown" ;;
    esac
}

# ── Docker installation ────────────────────────────────────────────
# Attempts to install Docker when missing. On macOS, downloads Docker
# Desktop (manual install required). On Linux, installs via the
# official Docker apt/dnf repository. Always asks for confirmation
# before running sudo commands.
install_docker() {
    local os
    os="$(os_id)"

    case "$os" in
        macos)
            info "macOS detected. Docker Desktop must be installed manually."
            if command_exists brew; then
                info "Run: brew install --cask docker"
                if confirm "Run this now?"; then
                    brew install --cask docker
                    info "Docker Desktop installed. Open it from /Applications, complete the setup wizard, then re-run ./dev setup."
                fi
            else
                echo "  Download: https://desktop.docker.com/mac/main/arm64/Docker.dmg"
                echo "  (Intel Mac: https://desktop.docker.com/mac/main/amd64/Docker.dmg)"
                echo ""
                info "Open the .dmg, drag Docker to /Applications, launch it, complete the setup wizard, then re-run ./dev setup."
            fi
            ;;
        ubuntu|debian)
            info "Ubuntu/Debian detected. Installing Docker Engine via apt..."
            if ! confirm "Install Docker Engine + Compose plugin? (requires sudo)"; then
                echo "  Manual install: https://docs.docker.com/engine/install/ubuntu/"
                return 1
            fi
            # Remove old packages
            for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
                sudo apt-get remove -y "$pkg" >/dev/null 2>&1 || true
            done
            # Add Docker's official GPG key and repo
            sudo apt-get update -qq
            sudo apt-get install -y -qq ca-certificates curl
            sudo install -m 0755 -d /etc/apt/keyrings
            sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
            sudo chmod a+r /etc/apt/keyrings/docker.asc
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
            sudo apt-get update -qq
            sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            # Add user to docker group (avoids needing sudo for every command)
            sudo usermod -aG docker "$USER"
            ok "Docker installed. You may need to log out and back in for group changes to take effect."
            info "Run: newgrp docker    (to use Docker in this shell without logging out)"
            ;;
        fedora|rhel|centos|rocky|almalinux)
            info "Fedora/RHEL detected. Installing Docker Engine via dnf..."
            if ! confirm "Install Docker Engine + Compose plugin? (requires sudo)"; then
                echo "  Manual install: https://docs.docker.com/engine/install/fedora/"
                return 1
            fi
            sudo dnf -y remove docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-selinux docker-engine-selinux docker-engine 2>/dev/null || true
            sudo dnf -y install dnf-plugins-core
            sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
            sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            sudo systemctl enable --now docker
            sudo usermod -aG docker "$USER"
            ok "Docker installed and daemon started."
            ;;
        arch|manjaro)
            info "Arch Linux detected."
            if confirm "Install Docker via pacman? (requires sudo)"; then
                sudo pacman -S --noconfirm docker docker-compose
                sudo systemctl enable --now docker
                sudo usermod -aG docker "$USER"
                ok "Docker installed and daemon started."
            else
                echo "  Run: sudo pacman -S docker docker-compose"
                return 1
            fi
            ;;
        *)
            warn "Could not detect package manager. Install Docker manually:"
            echo "  https://docs.docker.com/engine/install/"
            return 1
            ;;
    esac

    # Verify installation
    if command_exists docker; then
        if docker info >/dev/null 2>&1; then
            ok "Docker is running."
            return 0
        else
            warn "Docker installed but daemon is not running."
            case "$os" in
                macos)
                    info "Launch Docker Desktop from /Applications, then re-run ./dev setup." ;;
                *)
                    info "Run: sudo systemctl enable --now docker   (then: newgrp docker)" ;;
            esac
        fi
    fi
    return 1
}

require_docker() {
    if ! command_exists docker; then
        warn "Docker is required but not installed."
        if install_docker; then
            return 0
        fi
        err "Docker installation was not completed. Re-run ./dev setup after installing."
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
# $PID_DIR so `dev down` and the INT/TERM trap can kill them reliably.
# Optional `--cwd DIR` makes the process run from a specific directory
# (uvicorn/celery must run from backend/, vite from frontend/).
start_bg() {
    local name="$1"; shift
    local cwd="${DEV_ROOT}"
    if [[ "${1:-}" == "--cwd" ]]; then
        cwd="$2"
        shift 2
    fi
    local logfile="${DEV_ROOT}/.logs/${name}.log"
    mkdir -p "$(dirname "$logfile")"
    info "Starting $name → ${logfile}"
    (
        cd "$cwd" || { err "Cannot cd to $cwd for $name"; exit 1; }
        # shellcheck disable=SC2068
        nohup "$@" >"$logfile" 2>&1 &
        echo $! > "${PID_DIR}/${name}.pid"
    )
}

kill_tracked() {
    local name="$1"
    local pidfile="${PID_DIR}/${name}.pid"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
            info "Stopping $name (pid $pid)"
            # Signal the whole process group first (covers children such as
            # uvicorn --reload subprocesses / celery pool workers). Fall back
            # to the individual PID when the process is not a group leader.
            kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
            sleep 1
            kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
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

# EXIT trap: remove only STALE PID files (processes already dead). Never
# kill processes on normal exit — otherwise `dev up` would tear down the
# stack it just started. Live PID files stay so `dev down` can stop them.
cleanup_stale_pidfiles() {
    local pidfile pid
    for pidfile in "${PID_DIR}"/*.pid; do
        [[ -e "$pidfile" ]] || continue
        pid="$(cat "$pidfile" 2>/dev/null || echo 0)"
        if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$pidfile"
        fi
    done
    return 0
}

# INT/TERM: kill tracked background processes (then EXIT removes PID files).
trap cleanup_all INT TERM
# EXIT: only clean up stale PID files — never kill running processes.
trap cleanup_stale_pidfiles EXIT

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
