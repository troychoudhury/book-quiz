#!/usr/bin/env bash
#==============================================================================
# Phase 02: Milestone & Task Planning
#==============================================================================
# Creates beads (issues) for all milestones and tasks. Uses bd CLI for
# persistent task tracking. Each task includes acceptance criteria derived
# from the ATDD approach.
#==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info()  { echo -e "\033[0;34m[PLAN]\033[0m  $*"; }
ok()    { echo -e "\033[0;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }

# Check if bd is available
if ! command -v bd &>/dev/null; then
    warn "bd CLI not found. Creating issues as JSONL directly."
    BD_AVAILABLE=false
else
    BD_AVAILABLE=true
fi

# --- Issue creation helper -----------------------------------------
create_issue() {
    local title="$1" description="$2" labels="$3" milestone="$4"
    local id

    if [[ "$BD_AVAILABLE" == true ]]; then
        # Use bd create; capture the ID from output
        id=$(bd create "$title" --description "$description" --label "$labels" 2>&1 | grep -oP 'created issue \K\S+' || echo "bd-$(date +%s%N)")
        bd update "$id" --milestone "$milestone" 2>/dev/null || true
    else
        # Fallback: append to issues.jsonl
        id="M${milestone}-$(date +%s%N | tail -c5)"
        echo "{\"id\":\"$id\",\"title\":\"$title\",\"description\":\"$description\",\"labels\":\"$labels\",\"milestone\":\"$milestone\",\"status\":\"open\"}" >> "${SCRIPT_DIR}/.beads/issues.jsonl"
    fi
    echo "$id"
}

# --- Milestones ----------------------------------------------------
create_milestones() {
    info "Creating project milestones and tasks..."

    # Milestone 0: Foundation
    info "--- Milestone 0: Project Foundation ---"

    create_issue \
        "Set up project repository structure" \
        "Create backend/ and frontend/ directory structures. Initialize Python venv, npm project, Docker Compose, pre-commit hooks. Verify 'make dev' starts both servers." \
        "infrastructure,setup" "0"

    create_issue \
        "Create database schema and migrations" \
        "Implement all tables from DATA_MODEL.md: users, books, questions, choices, quiz_attempts, quiz_answers. Include GIN trigram index for book search. Create Alembic migration." \
        "infrastructure,database" "0"

    create_issue \
        "Implement core FastAPI application skeleton" \
        "Create FastAPI app with CORS, error handlers, request ID middleware, health check endpoint (/api/v1/health). Structured logging with structlog." \
        "backend,infrastructure" "0"

    create_issue \
        "Implement authentication system" \
        "JWT-based auth with /auth/register, /auth/login, /auth/refresh endpoints. Password hashing (bcrypt), token generation/validation, user model. Include rate limiting on auth endpoints." \
        "backend,auth" "0"

    create_issue \
        "Set up React frontend skeleton with routing" \
        "React app with react-router-dom routes for all pages. Layout component with Header. Zustand store for auth state. React Query provider. Tailwind CSS setup." \
        "frontend,infrastructure" "0"

    # Milestone 1: Core Features
    info "--- Milestone 1: Core Features ---"

    create_issue \
        "Implement book search API endpoint" \
        "GET /api/v1/books with query parameter for fuzzy search on title and ISBN. Pagination. Response includes book metadata and question count. Write acceptance test FIRST." \
        "backend,feature,atdd" "1"

    create_issue \
        "Build landing page with search" \
        "Landing page with hero section, large search bar, and featured/example books. Search results displayed as book cards. Responsive design. Write Playwright acceptance test FIRST." \
        "frontend,feature,atdd" "1"

    create_issue \
        "Implement quiz start and answer API endpoints" \
        "POST /quizzes/start selects 10 random unanswered questions. POST /quizzes/{id}/answer records answer and returns correctness. POST /quizzes/{id}/complete finalizes attempt and returns score. Support both authenticated and guest flows." \
        "backend,feature,atdd" "1"

    create_issue \
        "Build quiz-taking page" \
        "Quiz page showing one question at a time with progress bar. Multiple-choice selection. Correct/incorrect feedback after each answer. Final score display. Guest email capture flow." \
        "frontend,feature,atdd" "1"

    create_issue \
        "Implement user profile API endpoint" \
        "GET /users/me/profile returns all books user has attempted with scores, attempts, and remaining questions. GET /users/me/books/{id}/progress returns detailed progress for a specific book." \
        "backend,feature,atdd" "1"

    create_issue \
        "Build profile page" \
        "Profile page showing book progress cards with attempt history, scores, and continue/retake buttons. Stats summary (total quizzes, questions answered)." \
        "frontend,feature,atdd" "1"

    # Milestone 2: Data & AI
    info "--- Milestone 2: Data Hydration & AI ---"

    create_issue \
        "Implement book data hydration background job" \
        "Celery task that fetches top 100 books per age group (6-18) from web sources. Parses book metadata (title, author, ISBN, description, age range). Stores in database with deduplication on ISBN." \
        "backend,data,ai" "2"

    create_issue \
        "Implement AI question generation background job" \
        "Celery task that uses OpenAI API to generate questions per chapter. Prompt engineering for theme, facts, characters, emotions, morals questions. Generates 10 questions per chapter with 4 choices each (1 correct, 3 plausible distractors). Includes 'none of the above' / 'all of the above' variants." \
        "backend,data,ai" "2"

    create_issue \
        "Implement hydration management API" \
        "POST /admin/hydrate to trigger hydration job. GET /admin/hydrate/{task_id}/status for progress. Admin key authentication." \
        "backend,data" "2"

    create_issue \
        "Build admin dashboard for hydration" \
        "Simple admin page to trigger hydration jobs, view progress, and see error logs. Protected by admin key." \
        "frontend,admin" "2"

    # Milestone 3: Polish & Quality
    info "--- Milestone 3: Polish & Quality ---"

    create_issue \
        "Implement comprehensive error handling and validation" \
        "Backend: consistent error response format, input validation with Pydantic, 404/401/403/429/500 handling. Frontend: error boundaries, toast notifications, loading states, empty states." \
        "backend,frontend,quality" "3"

    create_issue \
        "Add accessibility (a11y) features" \
        "Semantic HTML, ARIA labels, keyboard navigation, focus management, screen reader support for quiz flow. Color contrast compliance (WCAG AA)." \
        "frontend,quality,a11y" "3"

    create_issue \
        "Implement responsive design for all pages" \
        "Mobile-first responsive design. Test on viewports: 320px, 768px, 1024px, 1440px. Touch-friendly quiz interactions. Mobile menu." \
        "frontend,quality,responsive" "3"

    create_issue \
        "Performance optimization" \
        "Backend: database query optimization, response caching (Redis), connection pooling. Frontend: code splitting, lazy loading, image optimization, bundle size analysis." \
        "backend,frontend,performance" "3"

    # Milestone 4: CI/CD & Deployment
    info "--- Milestone 4: CI/CD & Deployment ---"

    create_issue \
        "Set up GitHub Actions CI pipeline" \
        "CI workflow: lint (ruff + eslint + prettier), type-check (mypy), unit + integration tests (pytest + vitest), E2E tests (Playwright). Run on PR and main." \
        "devops,ci" "4"

    create_issue \
        "Set up CD pipeline and deployment" \
        "Build Docker images, push to registry. Deploy to Fly.io or Railway. Database migration automation. Health check verification post-deploy." \
        "devops,cd,deployment" "4"

    create_issue \
        "Configure monitoring and error tracking" \
        "Application monitoring (Sentry or similar), uptime monitoring, log aggregation. Alert on error rate spikes." \
        "devops,monitoring" "4"

    ok "All milestones and tasks created."
}

# --- Generate task dependency graph --------------------------------
create_dependency_graph() {
    info "Creating task dependency graph..."
    cat > "${SCRIPT_DIR}/docs/TASK_DEPS.md" << 'EOF'
# Task Dependencies & Execution Order

```
Milestone 0 (Foundation) ─────────────────────────────────────────
  ┌─ M0.1: Repo structure
  ├─ M0.2: DB schema (depends on M0.1)
  ├─ M0.3: FastAPI skeleton (depends on M0.1)
  ├─ M0.4: Auth system (depends on M0.3, M0.2)
  └─ M0.5: React skeleton (depends on M0.1)

Milestone 1 (Core Features) ──────────────────────────────────────
  ┌─ M1.1: Book search API (depends on M0.3, M0.2)
  ├─ M1.2: Landing page (depends on M0.5, M1.1)
  ├─ M1.3: Quiz API (depends on M0.4, M0.2)
  ├─ M1.4: Quiz page (depends on M0.5, M1.3)
  ├─ M1.5: Profile API (depends on M0.4, M1.3)
  └─ M1.6: Profile page (depends on M0.5, M1.5)

Milestone 2 (Data & AI) ──────────────────────────────────────────
  ┌─ M2.1: Book hydration (depends on M0.2, M0.3)
  ├─ M2.2: AI question gen (depends on M2.1)
  ├─ M2.3: Hydration API (depends on M2.1, M2.2)
  └─ M2.4: Admin dashboard (depends on M2.3)

Milestone 3 (Polish) ─────────────────────────────────────────────
  ┌─ M3.1: Error handling (depends on M1.*)
  ├─ M3.2: Accessibility (depends on M1.*)
  ├─ M3.3: Responsive design (depends on M1.*)
  └─ M3.4: Performance (depends on M1.*)

Milestone 4 (CI/CD) ──────────────────────────────────────────────
  ┌─ M4.1: CI pipeline (depends on M0.*)
  ├─ M4.2: CD pipeline (depends on M4.1, M1.*)
  └─ M4.3: Monitoring (depends on M4.2)
```
EOF
    ok "TASK_DEPS.md created."
}

# --- Acceptance criteria summary ----------------------------------
create_acceptance_criteria() {
    info "Creating acceptance criteria checklist..."
    cat > "${SCRIPT_DIR}/docs/ACCEPTANCE_CRITERIA.md" << 'EOF'
# Acceptance Criteria Checklist

Each feature must pass these gates before being marked complete:

## Search & Discovery
- [ ] User can search by book title (partial match works)
- [ ] User can search by ISBN-10 and ISBN-13
- [ ] Search results show book cover, title, author, and question count
- [ ] Empty search shows helpful message
- [ ] No results shows "no books found" message
- [ ] Search works on mobile (320px width)

## Quiz Flow
- [ ] Quiz starts with 10 randomly selected questions
- [ ] Questions display one at a time with progress indicator
- [ ] Each answer shows immediate correct/incorrect feedback
- [ ] Quiz complete shows score with percentage
- [ ] Guest user sees email capture + login/signup prompt
- [ ] Authenticated user's results are saved automatically
- [ ] Retaking a quiz excludes previously answered questions
- [ ] When all questions exhausted, user is asked to retake
- [ ] Each retake is saved as a separate attempt

## Authentication
- [ ] User can register with email + password + display name
- [ ] User can login with email + password
- [ ] Token refresh works transparently
- [ ] Invalid credentials show clear error message
- [ ] Auth state persists across page reloads

## Profile
- [ ] Profile shows all attempted books with scores
- [ ] Each book shows attempt history and remaining questions
- [ ] Stats summary is accurate (total quizzes, questions answered)
- [ ] Clicking a book navigates to its detail/quiz page

## Admin / Hydration
- [ ] Hydration can be triggered via API
- [ ] Progress can be polled during hydration
- [ ] Hydrated books appear in search
- [ ] AI-generated questions are diverse and chapter-specific
- [ ] Questions are not duplicated on re-hydration

## Cross-Cutting
- [ ] All pages load in < 3 seconds on 3G
- [ ] All interactive elements are keyboard accessible
- [ ] Color contrast meets WCAG AA (4.5:1)
- [ ] Error states have user-friendly messages
- [ ] API errors are handled gracefully with retry options
EOF
    ok "ACCEPTANCE_CRITERIA.md created."
}

# --- Main ----------------------------------------------------------
main() {
    info "=== Phase 02: Milestone & Task Planning ==="
    create_milestones
    create_dependency_graph
    create_acceptance_criteria

    ok "Phase 02 complete."
    echo ""
    echo "  Generated:"
    echo "    docs/TASK_DEPS.md"
    echo "    docs/ACCEPTANCE_CRITERIA.md"
    echo "    Issues created in bd tracker"
    echo ""
    echo "  Run 'bd ready' to see available work."
}

main "$@"
