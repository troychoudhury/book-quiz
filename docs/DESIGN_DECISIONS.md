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
