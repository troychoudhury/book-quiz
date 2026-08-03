# Implement book search API endpoint

**Bead**: book-quiz-2u3 | **Status**: status_plan

## Description

GET /api/v1/books with query parameter for fuzzy search on title and ISBN. Pagination. Response includes book metadata and question count. Write acceptance test FIRST.

## Agent Log

| Date | Agent | Action | Summary |
|------|-------|--------|----------|
| 2026-08-01T04:49:58Z | system | created | Issue filed |
| 2026-08-03 | tech-lead | claim | Claimed for implementation |

## Architecture Plan

### Current State Analysis

The `GET /api/v1/books` endpoint in `backend/app/api/books.py` already exists with:
- ILIKE-based title/ISBN search (`%term%` pattern matching)
- Pagination (page/size query params)
- Response includes `question_count` via `len(b.questions)`
- Book detail endpoint (`GET /api/v1/books/{book_id}`) also exists

### Gap Analysis (vs DATA_MODEL + API_DESIGN specs)

1. **Fuzzy search**: The DATA_MODEL specifies a `gin_trgm_ops` GIN index on `books.title`. The current ILIKE approach does NOT use trigram similarity — it only does basic substring matching. True fuzzy search requires:
   - Enabling the `pg_trgm` PostgreSQL extension via Alembic migration
   - Creating the GIN index `idx_books_title_trgm`
   - Optionally using `similarity()` / `word_similarity()` for ranked results

2. **Acceptance tests**: No acceptance tests exist. ATDD requires tests written FIRST.

3. **Performance**: The `question_count` field triggers N+1 on the questions relationship — already mitigated by `lazy="selectin"` on the relationship.

### Design Decision: Trigram vs Keep ILIKE

**Decision**: Add pg_trgm extension and GIN index, but keep ILIKE as the primary search operator for now. The ILIKE approach is already functional and sufficient for the current scale. Adding the GIN index accelerates the ILIKE queries. A future enhancement can add `ORDER BY similarity(title, query)` for ranked results.

**Rationale**: 
- ILIKE with a trigram GIN index is performant and matches user expectations for book search
- Full `similarity()` ranking adds complexity without immediate user-facing benefit
- The GIN index is already specified in DATA_MODEL.md

### Required Changes

1. **Migration**: Create Alembic migration to:
   - `CREATE EXTENSION IF NOT EXISTS pg_trgm`
   - `CREATE INDEX idx_books_title_trgm ON books USING gin (title gin_trgm_ops)`
   - `CREATE INDEX idx_books_isbn ON books (isbn)` (if not exists)

2. **Acceptance tests** (`tests/acceptance/test_book_search.py`):
   - Test searching by partial title returns matching books
   - Test searching by exact ISBN returns the correct book
   - Test empty query returns all books (paginated)
   - Test pagination (page 2 returns different results)
   - Test search with no results returns empty list
   - Test book detail endpoint returns full book info

3. **No code changes needed to `backend/app/api/books.py`** — the existing ILIKE logic is sufficient and the GIN index accelerates it automatically.

## Review Feedback

*No review feedback yet.*

## Implementation Notes

*Not yet implemented.*

## Test Results

*Not yet tested.*
