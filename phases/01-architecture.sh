#!/usr/bin/env bash
#==============================================================================
# Phase 01: Architecture & Design
#==============================================================================
# Produces:
#   - docs/ARCHITECTURE.md       — System architecture, component diagram
#   - docs/DATA_MODEL.md          — Database schema, entity relationships
#   - docs/API_DESIGN.md          — REST API endpoints, request/response shapes
#   - docs/DESIGN_DECISIONS.md    — Key design decisions & tradeoffs (ADR)
#   - docs/COMPONENT_TREE.md      — Frontend component hierarchy
#==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$SCRIPT_DIR/docs"
mkdir -p "$DOCS_DIR"

info()  { echo -e "\033[0;34m[ARCH]\033[0m  $*"; }
ok()    { echo -e "\033[0;32m[OK]\033[0m    $*"; }

# --- Architecture Document -----------------------------------------
create_architecture_doc() {
    info "Creating ARCHITECTURE.md..."
    cat > "$DOCS_DIR/ARCHITECTURE.md" << 'EOF'
# Book Quiz — System Architecture

## Overview

Book Quiz is a web application that lets readers search for books and take
AI-generated quizzes to test comprehension. It targets individual readers
(ages 6–18+) rather than schools or institutions.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Browser    │────▶│   Cloudflare │────▶│   React SPA      │
│   (Client)   │     │   CDN / WAF  │     │   (Vite-built)   │
└──────────────┘     └──────────────┘     └────────┬─────────┘
                                                   │ REST/JSON
                                                   ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│   OpenAI API │◀────│   FastAPI    │────▶│   PostgreSQL     │
│ (Q gen only) │     │   Backend    │     │   (Primary DB)   │
└──────────────┘     └──────┬───────┘     └──────────────────┘
                            │
                   ┌────────▼───────┐
                   │   Redis        │
                   │   (Cache/Task) │
                   └────────────────┘
                            │
                   ┌────────▼───────┐
                   │   Celery       │
                   │   (Background) │
                   └────────────────┘
```

## Architectural Principles

1. **Separation of Concerns** — Backend API is purely REST; frontend is a
   single-page application. AI question generation is a background job.
2. **Stateless API** — JWT-based auth; no server-side sessions.
3. **Read-over-write optimization** — Quiz-taking is read-heavy; caching
   strategies prioritize reads.
4. **Eventual consistency for analytics** — Quiz results may lag slightly
   but are never lost (Celery task queue).
5. **Observability by default** — Structured logging, request IDs, health
   check endpoints.

## Component Details

### Frontend (React + TypeScript + Vite)

- **Routing**: react-router-dom v7 with lazy-loaded pages
- **State**: Zustand for global state; React Query for server-state caching
- **Styling**: Tailwind CSS for utility-first design
- **Testing**: Vitest (unit), React Testing Library (integration), Playwright (E2E)

### Backend (FastAPI + Python 3.12)

- **API Layer**: FastAPI with Pydantic v2 for validation/serialization
- **ORM**: SQLAlchemy 2.0 with async sessions
- **Migrations**: Alembic
- **Auth**: JWT access tokens (short-lived) + refresh tokens (long-lived)
- **Background Tasks**: Celery with Redis broker for AI question generation
- **Testing**: pytest with async support, factory_boy for fixtures

### Database (PostgreSQL 16)

- Primary data store for books, questions, users, and quiz attempts
- Full-text search via GIN indexes for book search
- Row-level security consideration for user data isolation

### Cache (Redis)

- API response caching for book lists and popular quizzes
- Session/rate-limiting token storage
- Celery broker

## Security

- HTTPS only (enforced via Cloudflare)
- JWT tokens with RS256 signing
- Rate limiting on auth endpoints
- Input sanitization (Pydantic + parameterized queries)
- CORS restricted to known origins
- Content-Security-Policy headers

## Deployment Architecture

```
GitHub → GitHub Actions → Docker images → Container Registry
                                          │
                                          ▼
                                  ┌──────────────┐
                                  │  Fly.io /     │
                                  │  Railway /    │
                                  │  Render       │
                                  └──────────────┘
```
EOF
    ok "ARCHITECTURE.md created."
}

# --- Data Model ---------------------------------------------------
create_data_model_doc() {
    info "Creating DATA_MODEL.md..."
    cat > "$DOCS_DIR/DATA_MODEL.md" << 'EOF'
# Book Quiz — Data Model

## Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│    User      │       │  QuizAttempt     │       │    Book      │
├──────────────┤       ├──────────────────┤       ├──────────────┤
│ id (PK)      │──┐    │ id (PK)          │    ┌──│ id (PK)      │
│ email        │  │    │ user_id (FK)     │────┘  │ title        │
│ password_hash│  │    │ book_id (FK)     │────┐  │ author       │
│ display_name │  └───▶│ started_at       │    │  │ isbn         │
│ created_at   │       │ completed_at     │    │  │ cover_url    │
│ is_active    │       │ score            │    │  │ age_range    │
└──────────────┘       │ total_questions  │    │  │ description  │
                       │ attempt_number   │    │  │ created_at   │
                       └────────┬─────────┘    │  └──────────────┘
                                │              │
                                │              │
                       ┌────────▼─────────┐    │
                       │  QuizAnswer      │    │
                       ├──────────────────┤    │
                       │ id (PK)          │    │
                       │ attempt_id (FK)  │    │
                       │ question_id (FK) │──┐ │
                       │ selected_choice  │  │ │
                       │ is_correct       │  │ │
                       │ answered_at      │  │ │
                       └──────────────────┘  │ │
                                             │ │
                       ┌──────────────────┐  │ │
                       │    Question      │◄─┘ │
                       ├──────────────────┤    │
                       │ id (PK)          │    │
                       │ book_id (FK)     │────┘
                       │ chapter          │
                       │ chapter_title    │
                       │ question_text    │
                       │ question_type    │
                       │ difficulty       │
                       │ created_at       │
                       └────────┬─────────┘
                                │
                       ┌────────▼─────────┐
                       │    Choice        │
                       ├──────────────────┤
                       │ id (PK)          │
                       │ question_id (FK) │
                       │ choice_text      │
                       │ is_correct       │
                       │ position         │
                       └──────────────────┘
```

## Table Definitions

### users
| Column         | Type         | Constraints            |
|----------------|--------------|------------------------|
| id             | UUID         | PK, default gen_random_uuid() |
| email          | VARCHAR(255) | UNIQUE, NOT NULL, indexed |
| password_hash  | VARCHAR(255) | NOT NULL               |
| display_name   | VARCHAR(100) | NOT NULL               |
| created_at     | TIMESTAMPTZ  | NOT NULL, default now()|
| is_active      | BOOLEAN      | NOT NULL, default true |

### books
| Column      | Type         | Constraints            |
|-------------|--------------|------------------------|
| id          | UUID         | PK                     |
| title       | VARCHAR(500) | NOT NULL, indexed      |
| author      | VARCHAR(300) | NOT NULL               |
| isbn        | VARCHAR(13)  | UNIQUE, indexed        |
| cover_url   | TEXT         |                        |
| age_range   | INT4RANGE    |                        |
| description | TEXT         |                        |
| created_at  | TIMESTAMPTZ  | NOT NULL               |

### questions
| Column         | Type         | Constraints            |
|----------------|--------------|------------------------|
| id             | UUID         | PK                     |
| book_id        | UUID         | FK → books.id, indexed |
| chapter        | INTEGER      | NOT NULL               |
| chapter_title  | VARCHAR(500) |                        |
| question_text  | TEXT         | NOT NULL               |
| question_type  | VARCHAR(20)  | 'multiple_choice' only |
| difficulty     | VARCHAR(10)  | 'easy','medium','hard' |
| created_at     | TIMESTAMPTZ  | NOT NULL               |

### choices
| Column       | Type         | Constraints               |
|--------------|--------------|---------------------------|
| id           | UUID         | PK                        |
| question_id  | UUID         | FK → questions.id, CASCADE|
| choice_text  | TEXT         | NOT NULL                  |
| is_correct   | BOOLEAN      | NOT NULL, default false   |
| position     | SMALLINT     | NOT NULL                  |

### quiz_attempts
| Column          | Type         | Constraints            |
|-----------------|--------------|------------------------|
| id              | UUID         | PK                     |
| user_id         | UUID         | FK → users.id, indexed |
| book_id         | UUID         | FK → books.id, indexed |
| started_at      | TIMESTAMPTZ  | NOT NULL               |
| completed_at    | TIMESTAMPTZ  |                        |
| score           | INTEGER      |                        |
| total_questions | INTEGER      | NOT NULL, default 10   |
| attempt_number  | INTEGER      | NOT NULL               |

### quiz_answers
| Column          | Type         | Constraints                    |
|-----------------|--------------|--------------------------------|
| id              | UUID         | PK                             |
| attempt_id      | UUID         | FK → quiz_attempts.id, CASCADE |
| question_id     | UUID         | FK → questions.id              |
| selected_choice | UUID         | FK → choices.id                |
| is_correct      | BOOLEAN      | NOT NULL                       |
| answered_at     | TIMESTAMPTZ  | NOT NULL                       |

## Indexes

```sql
-- Book search
CREATE INDEX idx_books_title_trgm ON books USING gin (title gin_trgm_ops);
CREATE INDEX idx_books_isbn ON books (isbn);

-- Quiz deduplication
CREATE UNIQUE INDEX idx_unique_attempt ON quiz_attempts (user_id, book_id, attempt_number);

-- Performance
CREATE INDEX idx_questions_book_chapter ON questions (book_id, chapter);
CREATE INDEX idx_quiz_answers_attempt ON quiz_answers (attempt_id);
```
EOF
    ok "DATA_MODEL.md created."
}

# --- API Design ---------------------------------------------------
create_api_design_doc() {
    info "Creating API_DESIGN.md..."
    cat > "$DOCS_DIR/API_DESIGN.md" << 'EOF'
# Book Quiz — API Design

Base URL: `/api/v1`

## Authentication

All `/api/v1/users/*` endpoints (except register/login) require:
```
Authorization: Bearer <access_token>
```

### POST /auth/register
```json
// Request
{ "email": "user@example.com", "password": "s3cur3P@ss!", "display_name": "Alice" }
// Response 201
{ "id": "uuid", "email": "user@example.com", "display_name": "Alice" }
```

### POST /auth/login
```json
// Request
{ "email": "user@example.com", "password": "s3cur3P@ss!" }
// Response 200
{ "access_token": "jwt...", "refresh_token": "jwt...", "token_type": "bearer" }
```

### POST /auth/refresh
```json
// Request
{ "refresh_token": "jwt..." }
// Response 200
{ "access_token": "new_jwt...", "refresh_token": "new_jwt..." }
```

## Books

### GET /books?q=harry+potter&page=1&size=20
```json
// Response 200
{
  "items": [
    {
      "id": "uuid", "title": "Harry Potter and the Sorcerer's Stone",
      "author": "J.K. Rowling", "isbn": "9780590353427",
      "cover_url": "https://...", "age_range": [8, 12],
      "question_count": 150
    }
  ],
  "total": 1, "page": 1, "size": 20
}
```

### GET /books/{book_id}
```json
// Response 200
{
  "id": "uuid", "title": "...", "author": "...", "isbn": "...",
  "cover_url": "...", "age_range": [8, 12], "description": "...",
  "chapters": 17, "total_questions": 150,
  "user_progress": { "attempts_completed": 2, "questions_answered": 20 }
}
```

## Quizzes

### POST /quizzes/start
```json
// Request (no auth — guest quiz)
{ "book_id": "uuid" }
// Request (authenticated)
{ "book_id": "uuid" }

// Response 201
{
  "attempt_id": "uuid",
  "questions": [
    {
      "id": "uuid", "question_number": 1,
      "question_text": "What is the main theme of Chapter 1?",
      "chapter": 1, "chapter_title": "The Boy Who Lived",
      "choices": [
        { "id": "uuid", "text": "Love conquers all", "position": 0 },
        { "id": "uuid", "text": "Power corrupts", "position": 1 },
        { "id": "uuid", "text": "Knowledge is power", "position": 2 },
        { "id": "uuid", "text": "Revenge is sweet", "position": 3 }
      ]
    }
    // ... 9 more questions
  ]
}
```

### POST /quizzes/{attempt_id}/answer
```json
// Request
{ "question_id": "uuid", "choice_id": "uuid" }
// Response 200
{ "is_correct": true, "correct_choice_id": "uuid", "question_number": 1 }
```

### POST /quizzes/{attempt_id}/complete
```json
// Request (guest — optionally provide email)
{ "email": "user@example.com" }
// Response 200
{
  "attempt_id": "uuid", "score": 8, "total": 10,
  "percentage": 80, "completed_at": "2025-01-01T00:00:00Z",
  "results": [
    { "question_id": "uuid", "question_text": "...",
      "selected_choice": "Love conquers all", "correct_choice": "Love conquers all",
      "is_correct": true, "chapter": 1 }
  ]
}
```

## User Profile

### GET /users/me/profile
```json
// Response 200
{
  "id": "uuid", "email": "user@example.com", "display_name": "Alice",
  "total_quizzes": 5, "total_questions_answered": 50,
  "books": [
    {
      "book_id": "uuid", "title": "Harry Potter...", "author": "...",
      "cover_url": "...", "attempts": [
        { "attempt_number": 1, "score": 7, "total": 10, "completed_at": "..." },
        { "attempt_number": 2, "score": 9, "total": 10, "completed_at": "..." }
      ],
      "best_score": 90, "total_questions_answered": 20,
      "remaining_questions": 130
    }
  ]
}
```

### GET /users/me/books/{book_id}/progress
```json
// Response 200
{
  "book_id": "uuid", "title": "...",
  "attempts_completed": 2, "total_questions_answered": 20,
  "total_questions": 150, "remaining_questions": 130,
  "can_retake": true,
  "attempts": [/* attempt history */]
}
```

## Admin / Background

### POST /admin/hydrate
```json
// Request (requires admin key)
{ "age": 10, "limit": 100 }
// Response 202
{ "task_id": "uuid", "status": "processing", "message": "Hydration job started" }
```

### GET /admin/hydrate/{task_id}/status
```json
// Response 200
{ "task_id": "uuid", "status": "completed", "books_processed": 100,
  "questions_generated": 1500, "errors": [] }
```
EOF
    ok "API_DESIGN.md created."
}

# --- Design Decisions (ADR) ---------------------------------------
create_design_decisions() {
    info "Creating DESIGN_DECISIONS.md..."
    cat > "$DOCS_DIR/DESIGN_DECISIONS.md" << 'EOF'
# Book Quiz — Architecture Decision Records

## ADR-001: Python/FastAPI Backend + React Frontend
**Status**: Accepted
**Date**: 2025-01

**Context**: Need a productive stack with strong AI/LLM integration.

**Decision**: Python FastAPI (backend) + React TypeScript (frontend).

**Rationale**:
- Python has the best OpenAI SDK and ecosystem for AI integration
- FastAPI provides automatic OpenAPI docs, async support, and Pydantic validation
- React has the largest component ecosystem and tooling maturity
- TypeScript prevents entire categories of frontend bugs

## ADR-002: PostgreSQL with GIN Trigrams for Search
**Status**: Accepted
**Date**: 2025-01

**Context**: Book search needs to handle partial title matches and typos.

**Decision**: PostgreSQL full-text search with `pg_trgm` extension for fuzzy
matching instead of Elasticsearch.

**Rationale**:
- Reduces operational complexity (one fewer service)
- `pg_trgm` GIN indexes handle fuzzy matching well for < 10K books
- Can migrate to Elasticsearch later if search becomes a bottleneck

## ADR-003: JWT with Short-Lived Access Tokens
**Status**: Accepted
**Date**: 2025-01

**Context**: Stateless auth for a single-page application.

**Decision**: JWT access tokens (15 min) + refresh tokens (7 days) stored in
httpOnly cookies.

**Rationale**:
- Stateless scaling (no server-side session store)
- Short-lived access tokens minimize stolen-token window
- httpOnly cookies prevent XSS token theft
- Refresh rotation adds security

## ADR-004: Question Generation as Background Celery Task
**Status**: Accepted
**Date**: 2025-01

**Context**: AI question generation can take 30–60s per book and must not block
the API.

**Decision**: Celery with Redis broker. API returns 202 Accepted with a
task ID for polling.

**Rationale**:
- Prevents request timeouts during AI generation
- Retry logic built into Celery
- Workers can be scaled independently
- Redis is already used for caching

## ADR-005: Acceptance Test Driven Development (ATDD)
**Status**: Accepted
**Date**: 2025-01

**Context**: Need confidence that features work as users experience them.

**Decision**: Write acceptance tests BEFORE implementation for every feature.
Use Playwright for E2E tests that simulate real user journeys.

**Rationale**:
- Tests serve as executable specifications
- Catches integration issues early
- Playwright provides reliable cross-browser testing
- Acceptance tests document expected behavior for new contributors

## ADR-006: Quiz Question Selection Algorithm
**Status**: Accepted
**Date**: 2025-01

**Context**: Users should get fresh questions on retakes.

**Decision**: Track answered question IDs per user per book. On quiz start,
select 10 random questions excluding previously answered ones. If all questions
exhausted, ask user if they want to retake (shuffle all questions).

**Rationale**:
- Simple to implement with a NOT IN subquery
- Fair to users (always getting new questions until exhausted)
- Clear UX signal when all questions have been seen

## ADR-007: Guest Quiz Flow
**Status**: Accepted
**Date**: 2025-01

**Context**: Users should be able to take a quiz without registering.

**Decision**: Allow guest quiz flow. On completion, prompt for email to send
results OR login/signup to save results. Guest attempts are ephemeral (not
persisted beyond the session unless the user provides email and creates an
account).

**Rationale**:
- Lowers barrier to trying the product
- Email capture provides conversion path
- Clear value proposition before asking for registration
EOF
    ok "DESIGN_DECISIONS.md created."
}

# --- Component Tree ------------------------------------------------
create_component_tree() {
    info "Creating COMPONENT_TREE.md..."
    cat > "$DOCS_DIR/COMPONENT_TREE.md" << 'EOF'
# Book Quiz — Frontend Component Tree

```
<App>
├── <Layout>
│   ├── <Header>
│   │   ├── <Logo />
│   │   ├── <SearchBar />            # Always visible, minimal
│   │   └── <AuthButtons>            # Login / Sign Up / User Menu
│   │       ├── <LoginButton />
│   │       ├── <SignUpButton />
│   │       └── <UserMenu>           # When authenticated
│   └── <Outlet />                   # react-router page content
│
├── Routes
│   ├── "/" → <LandingPage>
│   │   ├── <HeroSection>
│   │   │   ├── <Heading />
│   │   │   ├── <SubHeading />
│   │   │   └── <SearchBar />        # Primary search (large)
│   │   ├── <FeaturedBooks />        # Optional: popular books
│   │   └── <HowItWorks />
│   │
│   ├── "/search?q=..." → <SearchResultsPage>
│   │   ├── <SearchBar />            # Refine search
│   │   ├── <SearchResultList>
│   │   │   └── <BookCard />*        # One per result
│   │   │       ├── <BookCover />
│   │   │       ├── <BookInfo />
│   │   │       └── <StartQuizButton />
│   │   └── <Pagination />
│   │
│   ├── "/books/:id" → <BookDetailPage>
│   │   ├── <BookHeader>
│   │   │   ├── <BookCover />
│   │   │   └── <BookMeta />
│   │   ├── <BookDescription />
│   │   ├── <StartQuizButton />
│   │   └── <UserProgress />         # If authenticated
│   │
│   ├── "/quiz/:attemptId" → <QuizPage>
│   │   ├── <QuizProgress>
│   │   │   ├── <ProgressBar />
│   │   │   └── <QuestionCounter />  # "Question 3 of 10"
│   │   ├── <QuestionCard>
│   │   │   ├── <QuestionText />
│   │   │   ├── <ChoiceList>
│   │   │   │   └── <ChoiceButton />* # One per choice
│   │   │   └── <FeedbackOverlay />   # Correct/incorrect flash
│   │   └── <QuizNavigation>
│   │       ├── <NextButton />
│   │       └── <SubmitButton />     # On last question
│   │
│   ├── "/quiz/:attemptId/complete" → <QuizCompletePage>
│   │   ├── <ScoreDisplay>
│   │   │   ├── <ScoreCircle />      # Animated score
│   │   │   └── <ScoreMessage />
│   │   ├── <ResultBreakdown>
│   │   │   └── <ResultItem />*      # Per-question result
│   │   ├── <GuestEmailCapture />    # If not logged in
│   │   ├── <RetakeButton />
│   │   └── <BackToBooksButton />
│   │
│   ├── "/login" → <LoginPage>
│   │   └── <AuthForm mode="login" />
│   │
│   ├── "/signup" → <SignUpPage>
│   │   └── <AuthForm mode="signup" />
│   │
│   └── "/profile" → <ProfilePage>  # Requires auth
│       ├── <ProfileHeader>
│       │   ├── <Avatar />
│       │   └── <UserStats />
│       └── <BookProgressList>
│           └── <BookProgressCard />*
│               ├── <BookCover />
│               ├── <BookInfo />
│               ├── <AttemptHistory />
│               └── <ContinueButton />
```

## State Management

| State Category       | Tool              | Example                          |
|----------------------|-------------------|----------------------------------|
| Server state         | React Query       | Book list, quiz data, profile    |
| Auth state           | Zustand + cookies | JWT token, user info             |
| UI state             | useState / Zustand| Quiz progress, selected choices  |
| Form state           | React Hook Form   | Login, signup, email capture     |
| URL state            | react-router      | Search query, current page       |
EOF
    ok "COMPONENT_TREE.md created."
}

# --- Main ----------------------------------------------------------
main() {
    info "=== Phase 01: Architecture & Design ==="
    create_architecture_doc
    create_data_model_doc
    create_api_design_doc
    create_design_decisions
    create_component_tree

    ok "Phase 01 complete. All design documents in docs/"
    echo ""
    echo "  Generated:"
    echo "    docs/ARCHITECTURE.md"
    echo "    docs/DATA_MODEL.md"
    echo "    docs/API_DESIGN.md"
    echo "    docs/DESIGN_DECISIONS.md"
    echo "    docs/COMPONENT_TREE.md"
}

main "$@"
