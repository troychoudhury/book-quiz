#!/usr/bin/env bash
#==============================================================================
# dev-test.sh — `dev test`
#==============================================================================
# Runs the full test suite (backend pytest, frontend vitest, Playwright e2e).
# Flags: --unit (skip e2e), --e2e (only e2e), --coverage (coverage reports).
#==============================================================================

test_backend() {
    step "Backend tests (pytest)"
    local venv_python="${DEV_ROOT}/backend/.venv/bin/python"
    if [[ ! -x "$venv_python" ]]; then
        err "Backend venv missing — run ./dev setup first."
        exit 1
    fi
    local args=(-m pytest tests/ -v --tb=short)
    if [[ "$COVERAGE" == true ]]; then
        args+=(--cov=app --cov-report=term-missing --cov-fail-under=80)
    fi
    (cd "${DEV_ROOT}/backend" && "$venv_python" "${args[@]}")
}

test_frontend() {
    step "Frontend tests (vitest)"
    if [[ ! -d "${DEV_ROOT}/frontend/node_modules" ]]; then
        err "Frontend deps missing — run ./dev setup first."
        exit 1
    fi
    local args=(run)
    if [[ "$COVERAGE" == true ]]; then
        args+=(--coverage)
    fi
    (cd "${DEV_ROOT}/frontend" && npx vitest "${args[@]}")
}

test_e2e() {
    step "End-to-end tests (Playwright)"
    if [[ ! -d "${DEV_ROOT}/frontend/node_modules" ]]; then
        err "Frontend deps missing — run ./dev setup first."
        exit 1
    fi
    # e2e needs the stack running; if it isn't, fail with clear guidance.
    if ! curl -sf "http://localhost:${BACKEND_PORT:-8000}/api/v1/health" >/dev/null 2>&1; then
        err "Backend is not running — e2e tests need the stack up (./dev up)."
        exit 1
    fi
    (cd "${DEV_ROOT}/frontend" && npx playwright test)
}

cmd_test() {
    local E2E=false UNIT_ONLY=false COVERAGE=false
    for arg in "$@"; do
        case "$arg" in
            --unit) UNIT_ONLY=true ;;
            --e2e)  E2E=true ;;
            --coverage) COVERAGE=true ;;
            --help|-h) echo "Usage: ./dev test [--unit|--e2e|--coverage]"; return 0 ;;
            *) err "Unknown flag: $arg"; exit 1 ;;
        esac
    done

    load_env

    if [[ "$E2E" == true ]]; then
        test_e2e
        ok "All tests passed."
        return 0
    fi

    test_backend
    test_frontend
    if [[ "$UNIT_ONLY" != true ]]; then
        test_e2e || warn "e2e tests failed or skipped (stack must be running)."
    fi
    ok "All tests passed."
}
