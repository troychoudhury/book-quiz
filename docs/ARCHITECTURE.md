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
