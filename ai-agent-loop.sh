#!/usr/bin/env bash
#==============================================================================
# AI Coding Agent Loop — Automated Software Engineering Pipeline
#==============================================================================
# Reads PROJECTS.md for goals/features and executes a complete engineering
# lifecycle: Architecture → Milestones → Implementation → CI/CD →
# Validation → Bug Fixing. Loops until everything passes flawlessly.
#
# Usage:
#   ./ai-agent-loop.sh [--phase PHASE] [--dry-run] [--skip-tests] [--verbose]
#
# Environment:
#   OPENAI_API_KEY   Required for AI-generated book quiz questions
#   DATABASE_URL     PostgreSQL connection (default: postgresql://localhost:5432/bookquiz)
#==============================================================================

set -euo pipefail
IFS=$'\n\t'

# --- Configuration -----------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="book-quiz"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_DIR="${SCRIPT_DIR}/.logs/${TIMESTAMP}"
STATE_FILE="${SCRIPT_DIR}/.loop-state.json"
DRY_RUN=false
SKIP_TESTS=false
VERBOSE=false
START_PHASE="00"

# --- Color Output -------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }
phase() { echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
          echo -e "${CYAN}  PHASE $1: $2${NC}"
          echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }

# --- Args ---------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --phase) START_PHASE="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --skip-tests) SKIP_TESTS=true; shift ;;
        --verbose) VERBOSE=true; shift ;;
        --help) sed -n '2,15p' "$0"; exit 0 ;;
        *) err "Unknown flag: $1"; exit 1 ;;
    esac
done

# --- Bootstrap ----------------------------------------------------
mkdir -p "$LOG_DIR" phases config templates

log()  { echo "[$(date +%H:%M:%S)] $*" >> "${LOG_DIR}/loop.log"; }
vlog() { [[ "$VERBOSE" == true ]] && echo -e "${CYAN}[VERBOSE]${NC} $*"; }

# --- State Management ---------------------------------------------
get_state() { jq -r ".$1 // empty" "$STATE_FILE" 2>/dev/null || echo ""; }
set_state() {
    local key="$1" val="$2"
    local tmp; tmp=$(mktemp)
    [[ -f "$STATE_FILE" ]] && jq --arg k "$key" --arg v "$val" '.[$k]=$v' "$STATE_FILE" > "$tmp" \
      || echo "{}" | jq --arg k "$key" --arg v "$val" '.[$k]=$v' > "$tmp"
    mv -f "$tmp" "$STATE_FILE"
}

# --- Validation ---------------------------------------------------
validate_prerequisites() {
    info "Checking prerequisites..."
    local missing=()
    for cmd in jq git python3 node npm; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        err "Missing required tools: ${missing[*]}"
        err "Install them and re-run."
        exit 1
    fi
    if [[ ! -f "${SCRIPT_DIR}/PROJECTS.md" ]]; then
        err "PROJECTS.md not found! This file defines the project goals and features."
        exit 1
    fi
    ok "All prerequisites satisfied."
}

# --- Phase Runners ------------------------------------------------
run_phase() {
    local phase_num="$1" phase_name="$2" script_path="$3"
    local current; current=$(get_state "last_completed_phase")
    if [[ -n "$current" ]] && [[ "$phase_num" < "$START_PHASE" ]]; then
        info "Skipping Phase $phase_num (already completed: $current)"
        return 0
    fi
    phase "$phase_num" "$phase_name"
    log "=== Starting Phase $phase_num: $phase_name ==="

    if [[ -x "$script_path" ]]; then
        if [[ "$DRY_RUN" == true ]]; then
            info "[DRY-RUN] Would execute: $script_path"
        else
            "$script_path" 2>&1 | tee -a "${LOG_DIR}/phase-${phase_num}.log"
            local rc=${PIPESTATUS[0]}
            if [[ $rc -ne 0 ]]; then
                err "Phase $phase_num FAILED (exit code $rc). Check ${LOG_DIR}/phase-${phase_num}.log"
                set_state "phase_${phase_num}_status" "failed"
                return 1
            fi
        fi
    else
        warn "Phase script not found: $script_path (skipping)"
    fi

    set_state "last_completed_phase" "$phase_num"
    set_state "phase_${phase_num}_status" "completed"
    ok "Phase $phase_num: $phase_name — COMPLETE"
    return 0
}

#==============================================================================
# MAIN LOOP
#==============================================================================
main() {
    echo -e "${GREEN}"
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║     AI CODING AGENT LOOP — Book Quiz Platform        ║"
    echo "  ║     Automated Software Engineering Pipeline          ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    validate_prerequisites
    info "Logs: ${LOG_DIR}"
    info "State file: ${STATE_FILE}"
    [[ "$DRY_RUN" == true ]] && warn "DRY-RUN MODE: No changes will be made."

    local iteration=0 max_iterations=10

    while [[ $iteration -lt $max_iterations ]]; do
        iteration=$((iteration + 1))
        echo -e "\n${YELLOW}═══════════════ ITERATION ${iteration}/${max_iterations} ═══════════════${NC}"

        # Phase 0: Project Initialization & Tooling
        run_phase "00" "PROJECT INITIALIZATION & TOOLING" "${SCRIPT_DIR}/phases/00-init.sh" || continue

        # Phase 1: Architecture & Design
        run_phase "01" "ARCHITECTURE & DESIGN" "${SCRIPT_DIR}/phases/01-architecture.sh" || continue

        # Phase 2: Milestone & Task Planning
        run_phase "02" "MILESTONE & TASK PLANNING" "${SCRIPT_DIR}/phases/02-milestones.sh" || continue

        # Phase 3: Implementation (ATDD Loop)
        run_phase "03" "IMPLEMENTATION (ATDD)" "${SCRIPT_DIR}/phases/03-implement.sh" || continue

        # Phase 4: CI/CD Pipeline
        run_phase "04" "CI/CD PIPELINE" "${SCRIPT_DIR}/phases/04-cicd.sh" || continue

        # Phase 5: End-to-End Validation
        run_phase "05" "END-TO-END VALIDATION" "${SCRIPT_DIR}/phases/05-validate.sh" || continue

        # Phase 6: Bug Discovery & Fix Loop
        run_phase "06" "BUG DISCOVERY & FIX LOOP" "${SCRIPT_DIR}/phases/06-fix-loop.sh" || continue

        # Check if all phases passed
        local all_pass=true
        for p in 00 01 02 03 04 05 06; do
            local s; s=$(get_state "phase_${p}_status")
            [[ "$s" != "completed" ]] && all_pass=false
        done

        if [[ "$all_pass" == true ]]; then
            echo -e "\n${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
            echo -e "${GREEN}║   🎉 ALL PHASES COMPLETE — PROJECT IS PRODUCTION-READY  ║${NC}"
            echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
            break
        else
            warn "Some phases did not pass. Re-running full loop..."
            set_state "last_completed_phase" ""
        fi
    done

    if [[ $iteration -ge $max_iterations ]]; then
        err "Reached max iterations ($max_iterations). Some issues may remain unresolved."
        exit 1
    fi

    # Final summary
    echo -e "\n${GREEN}=== FINAL PROJECT SUMMARY ===${NC}"
    echo "Logs:     ${LOG_DIR}"
    echo "State:    $(cat "$STATE_FILE" 2>/dev/null | jq . || echo '{}')"
    echo "Beads:    $(bd list --json 2>/dev/null | jq 'length' || echo 'N/A') issues tracked"
    ok "AI Coding Agent Loop completed successfully."
}

main "$@"
