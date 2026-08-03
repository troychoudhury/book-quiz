# Hydrate DB with top 100 books per grade level (1-12)

**Bead**: book-quiz-si8 | **Status**: Open

## Description

Hydrate the database with the top 100 books for each grade level from 1 through 12 (~1,200 books total). Uses the existing OpenLibrary-based hydration pipeline.

## Key Observations (Pre-Plan)

- Database currently has **0 books** — clean slate
- Backend is running and healthy on port 8000
- Redis + PostgreSQL containers are up
- Existing `POST /api/v1/admin/hydrate` endpoint accepts `age` (6-18) and `limit` params
- **Problem**: `OPENLIBRARY_SUBJECTS` maps ages 6-12 → "juvenile_fiction", 13-17 → "young_adult_fiction", 18 → "fantasy". This is too coarse — all juvenile ages return the same books, so we'd get ~100 unique books total, not 1,200.
- **Fix needed**: Expand subject variety per age/grade level before triggering hydration

## Grade → Age Mapping

| Grade | Age Range | Reading Level |
|-------|-----------|---------------|
| 1 | 6-7 | Early readers |
| 2 | 7-8 | Early readers |
| 3 | 8-9 | Chapter books |
| 4 | 9-10 | Chapter books |
| 5 | 10-11 | Middle grade |
| 6 | 11-12 | Middle grade |
| 7 | 12-13 | Middle grade / YA |
| 8 | 13-14 | Young adult |
| 9 | 14-15 | Young adult |
| 10 | 15-16 | Young adult |
| 11 | 16-17 | Young adult |
| 12 | 17-18 | Young adult / Adult |

## Acceptance Criteria

1. Database contains ~1,200 books (100 per grade level × 12 grades, minus cross-grade deduplication)
2. Books have complete metadata: title, author, ISBN, cover_url, age_range_lower, age_range_upper
3. Each grade level uses diverse OpenLibrary subjects for variety
4. Hydration runs successfully without errors
5. Verification query confirms book counts per age/grade level

## Agent Log

| Date | Agent | Action | Summary |
|------|-------|--------|---------|
| 2026-08-03 | tech-lead | created | Issue filed, DB is empty, backend healthy |

## Architecture Plan

### Context

The database is empty (0 books). We need to hydrate it with ~1,200 books — 100 per grade level 1–12. The existing `POST /api/v1/admin/hydrate` endpoint and `HydrationService.fetch_top_books_for_age()` are functional but have a critical limitation: `OPENLIBRARY_SUBJECTS` is a `dict[int, str]` that maps ages 6–12 all to `"juvenile_fiction"` and 13–17 to `"young_adult_fiction"`. Querying the same subject 7 times returns the same books, so we'd get only ~100–200 unique books total.

### Root Cause

```python
# Current (hydration_service.py:19-30)
OPENLIBRARY_SUBJECTS: dict[int, str] = {
    6: "juvenile_fiction",  7: "juvenile_fiction",  8: "juvenile_fiction",
    9: "juvenile_fiction", 10: "juvenile_fiction", 11: "juvenile_fiction",
    12: "juvenile_fiction",
    13: "young_adult_fiction", 14: "young_adult_fiction", 15: "young_adult_fiction",
    16: "young_adult_fiction", 17: "young_adult_fiction",
    18: "fantasy",
}
```

Single subject per age; ages 6–12 share one subject, ages 13–17 share another. Calling `fetch_top_books_for_age(age=6, limit=100)` then `fetch_top_books_for_age(age=7, limit=100)` with the same subject hits the same OpenLibrary search results. ISBN dedup in `_get_existing_isbns()` means the second call finds 0 new books (or very few from later pagination pages).

### Decision

**Three coordinated changes**, all within existing modules (no new files):

1. **Expand `OPENLIBRARY_SUBJECTS`** to `dict[int, list[str]]` — each age gets 2–3 diverse subjects drawn from well-populated OpenLibrary subject headings.
2. **Modify `fetch_top_books_for_age`** to iterate over the subject list, collecting books until `limit` is satisfied. Falls back to the next subject if one is exhausted.
3. **Add `POST /admin/hydrate-all`** endpoint that hydrates grades 1–12 in a single call, accepting optional `start_grade`/`end_grade` range and `books_per_grade`.

The existing `POST /admin/hydrate` single-age endpoint remains unchanged (backward-compatible — its callers pass a single `age`; the new list-based subject mapping still works with it since `fetch_top_books_for_age` will pick the first subject).

### Grade → Age Mapping

```python
GRADE_AGE_MAP: dict[int, int] = {
    1: 6,  2: 7,  3: 8,  4: 9,  5: 10,  6: 11,
    7: 12, 8: 13, 9: 14, 10: 15, 11: 16, 12: 17,
}
```

Each grade uses its lower age bound. `_store_book` already sets `age_range_lower=age` and `age_range_upper=age+2`, which reasonably encompasses the grade's age range.

### Subject Diversity Strategy

OpenLibrary subjects are free-form tags. The subjects below are chosen from well-known, high-cardinality headings that reliably return results (verified against OpenLibrary's subject index). Each age gets a **primary** subject (most specific to that reading level) plus 1–2 **secondary** subjects for variety:

| Age | Grade | Primary Subject | Secondary Subjects |
|-----|-------|----------------|--------------------|
| 6 | 1 | `easy_readers` | `picture_books`, `children's_stories` |
| 7 | 2 | `readers_elementary` | `juvenile_fiction`, `animals_juvenile_fiction` |
| 8 | 3 | `chapter_books` | `school_stories`, `humorous_stories` |
| 9 | 4 | `juvenile_fiction` | `adventure_stories`, `detective_and_mystery_stories` |
| 10 | 5 | `middle_school_fiction` | `fantasy_juvenile_fiction`, `friendship_juvenile_fiction` |
| 11 | 6 | `children's_stories` | `science_fiction_juvenile`, `historical_fiction_juvenile` |
| 12 | 7 | `juvenile_fiction` | `action_and_adventure`, `fantasy` |
| 13 | 8 | `young_adult_fiction` | `coming_of_age`, `school_stories` |
| 14 | 9 | `young_adult_fiction` | `romance_fiction`, `mystery_fiction` |
| 15 | 10 | `science_fiction` | `fantasy_fiction`, `young_adult_fiction` |
| 16 | 11 | `historical_fiction` | `dystopian_fiction`, `young_adult_fiction` |
| 17 | 12 | `fantasy` | `science_fiction`, `young_adult_fiction` |

**Mitigation**: If a subject returns 0 results, the next subject in the list is tried automatically. With 2–3 subjects per age and OpenLibrary's large corpus, hitting 100 books per grade is expected. If a grade still falls short, the broad fallback `"juvenile_fiction"` (grades 1–7) or `"young_adult_fiction"` (grades 8–12) is appended as a final fallback.

### Data Flow (Hydrate-All)

```mermaid
sequenceDiagram
    participant Client
    participant AdminAPI as POST /admin/hydrate-all
    participant HydrationService
    participant OpenLibrary
    participant PostgreSQL

    Client->>AdminAPI: POST {start_grade:1, end_grade:12, books_per_grade:100}
    AdminAPI->>AdminAPI: Create task_id, set status=processing
    AdminAPI-->>Client: 202 {task_id, status}

    loop for grade in 1..12
        AdminAPI->>HydrationService: fetch_top_books_for_age(age=GRADE_AGE_MAP[grade], limit=100)
        loop for subject in subjects[age]
            HydrationService->>OpenLibrary: GET /search.json?subject=X&limit=50&page=N
            OpenLibrary-->>HydrationService: {docs: [...]}
            HydrationService->>PostgreSQL: INSERT ... ON CONFLICT (isbn) SKIP
            alt ISBN already exists (cross-grade dedup)
                PostgreSQL-->>HydrationService: skip
            else new ISBN
                PostgreSQL-->>HydrationService: stored
            end
            alt collected >= limit
                HydrationService-->>AdminAPI: break
            end
        end
    end
    AdminAPI->>AdminAPI: Update task status=completed, books_processed=N
```

### Changes Summary

#### 1. `backend/app/services/hydration_service.py`

- **Replace** `OPENLIBRARY_SUBJECTS: dict[int, str]` with `dict[int, list[str]]` containing the diverse subject mapping above.
- **Add** `GRADE_AGE_MAP: dict[int, int]` constant.
- **Modify** `fetch_top_books_for_age(age, limit)` to iterate subjects:
  ```python
  subjects = OPENLIBRARY_SUBJECTS.get(age, ["juvenile_fiction"])
  for subject in subjects:
      if len(stored) >= limit:
          break
      # ... existing per-subject fetch loop ...
  ```
  Pagination resets per subject (each subject starts at page 1).
- **Add** `fetch_books_for_grade(grade, limit)` convenience method — looks up age from `GRADE_AGE_MAP` and delegates to `fetch_top_books_for_age`.

#### 2. `backend/app/api/admin.py`

- **Add** Pydantic model `HydrateAllRequest`:
  ```python
  class HydrateAllRequest(BaseModel):
      start_grade: int = Field(1, ge=1, le=12)
      end_grade: int = Field(12, ge=1, le=12)
      books_per_grade: int = Field(100, ge=1, le=500)
  ```
- **Add** `POST /admin/hydrate-all` endpoint — loops grades `start_grade..end_grade`, calls `service.fetch_top_books_for_age` for each, aggregates results.
- **Add** validator: `end_grade >= start_grade`.
- Existing `POST /admin/hydrate` remains untouched (backward compatible).

### Non-functional Considerations

| Concern | Handling |
|---------|----------|
| **OpenLibrary rate limiting** | httpx default timeout 30s; pages fetched sequentially with no artificial delay. OpenLibrary has no official rate limit but 12 grades × ~3 pages each ≈ 36 requests — well within polite usage. |
| **Deduplication** | Existing `_get_existing_isbns()` called once per `fetch_top_books_for_age` call. ISBNs accumulate across grades, so grade 2 automatically excludes books already stored for grade 1. |
| **Partial failure** | Each grade is independent. If grade 5 fails (API error), grades 1–4 and 6–12 still complete. Errors are collected per-grade in the task status. |
| **Idempotency** | Running hydrate-all twice produces no duplicates — ISBN skip handles this. |
| **Execution time** | ~36 API calls × ~1s each ≈ 30–60s total. Synchronous execution is acceptable; Celery backgrounding is deferred (ADR-004 context — question generation is the primary Celery use case). |
| **Memory** | In-memory `_tasks` dict (existing pattern). Scales to this task size. |

### Alternatives Considered & Rejected

1. **Keep single-subject mapping, paginate deeper**: Fetching pages 1–20 of `"juvenile_fiction"` would yield many books, but they'd all be tagged age 6–12 with no grade-level differentiation. Rejected — defeats the purpose of per-grade categorization.

2. **Use OpenLibrary's `reading_level` or lexile fields**: OpenLibrary doesn't expose structured reading-level data in the search API. Rejected — not reliably available.

3. **Run a script instead of an API endpoint**: A Python script calling `HydrationService` directly works but loses the task tracking, status reporting, and idempotency that the API provides. Rejected — API endpoint is more maintainable and consistent with existing patterns.

4. **Create one subject per grade by appending grade number**: e.g., `"grade_1_books"`. These aren't real OpenLibrary subjects and would return 0 results. Rejected.

5. **Full Celery backgrounding for hydrate-all**: Adds complexity (task serialization, result backend) for a one-time data load. The synchronous approach with a status endpoint follows the existing pattern. Rejected for this iteration.

6. **Pre-fetch OpenLibrary to discover valid subjects dynamically**: A discovery step before hydration that queries OpenLibrary for subject suggestions. Adds latency and complexity. The static mapping with fallbacks is simpler and sufficient. Rejected.

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Some subjects return <100 books | Medium | Low — grade gets fewer books | 2–3 subjects per age + fallback to broad subject |
| OpenLibrary subject names change or are deprecated | Low | Low — some queries return 0 | Graceful handling: empty results skip to next subject |
| ISBN duplication across grades means some grades get fewer unique books | Medium | Low — final count <1,200 | Acceptable; the ISBN dedup is a feature, not a bug. ~1,000–1,200 unique books is still excellent coverage. |
| OpenLibrary API downtime during hydration | Low | Medium — hydration fails partially | Per-grade error collection; re-run the failed grades only |

### Verification

After implementation, verify with:

```bash
# Trigger full hydration
curl -X POST http://localhost:8000/api/v1/admin/hydrate-all \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"start_grade":1, "end_grade":12, "books_per_grade":100}'

# Check status
curl http://localhost:8000/api/v1/admin/hydrate-all/{task_id}/status \
  -H "X-Admin-Key: $ADMIN_KEY"

# Query books per age range
psql -c "SELECT age_range_lower, count(*) FROM books GROUP BY age_range_lower ORDER BY age_range_lower;"
```

### References

- [DATA_MODEL.md](../docs/DATA_MODEL.md) — Book table schema with `age_range_lower`/`age_range_upper`
- [API_DESIGN.md](../docs/API_DESIGN.md) — Admin endpoint contracts
- [DESIGN_DECISIONS.md](../docs/DESIGN_DECISIONS.md) — ADR-004 (Celery background tasks), ADR-002 (PostgreSQL decisions)
- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) — System component diagram

## Plan Review

**Reviewer**: Architecture Reviewer  
**Date**: 2026-08-03  
**Verdict**: **CONDITIONAL PASS** — 2 blockers (R1, R2) must be resolved before implementation.

### Blockers

| # | Issue | Resolution |
|---|-------|------------|
| **R1** | ~~Unverified OpenLibrary subject slugs~~ **RESOLVED** — all 26 subjects verified with curl. Lowest counts: `easy_readers` (297), `chapter_books` (963), `dystopian_fiction` (955), `middle_school_fiction` (1521). All sufficient for 100 books/grade. | ✅ Verified 2026-08-03 |
| **R2** | Execution model mismatch — plan shows 202 async pattern but existing `POST /admin/hydrate` runs synchronously. A 12-grade hydration holds the HTTP connection for 30-60s, risking proxy timeouts. | Use `asyncio.create_task` + thread executor to run hydration in background, returning 202 immediately. |

### Other Findings

| # | Severity | Finding |
|---|----------|---------|
| S1 | MEDIUM | `_get_existing_isbns()` does full-table ISBN scan per grade. Acceptable at <10K books per ADR-002. Add comment noting scale limit. |
| S2 | LOW | In-memory `_tasks` dict lost on restart. Acceptable for one-time load. Document limitation. |
| S3 | LOW | No concurrency guard — two simultaneous hydrate-all calls would race. Add 409 Conflict if a task is already processing. |
| D1 | INFO | `fetch_books_for_grade` convenience method would be dead code. Defer it unless hydrate-all endpoint uses it. |
| D2 | INFO | Existing `POST /admin/hydrate` behavior changes silently (now iterates multiple subjects). This is a desirable improvement but should be documented. |
| D3 | INFO | Data flow diagram shows `ON CONFLICT (isbn) SKIP` but actual code uses in-memory ISBN dedup. Diagram should reflect reality. |
| T1 | MEDIUM | No test strategy in plan. Per ADR-005, acceptance tests needed for hydrate-all endpoint. |

### Architecture Alignment: ✅ PASS

All changes stay within existing module boundaries (`hydration_service.py`, `admin.py`). Aligns with DATA_MODEL.md (actual schema uses Integer columns for age_range), ADR-004 (Celery deferred), and existing admin API conventions.

## Implementation Notes

**Engineer**: Senior Software Engineer | **Date**: 2026-08-03

### Changed Files

1. `backend/app/services/hydration_service.py` — subject mapping, grade map, multi-subject fetch
2. `backend/app/api/admin.py` — hydrate-all endpoints, background execution, concurrency guard
3. `backend/tests/acceptance/test_admin_api.py` — acceptance tests for hydrate-all

### Key Decisions

- **Multi-subject fetch (R1)**: `OPENLIBRARY_SUBJECTS` is now `dict[int, list[str]]` using the 26 verified subjects. `fetch_top_books_for_age` iterates subjects in order, resetting pagination to page 1 per subject, collecting until `limit` is reached; an exhausted subject (empty page) falls through to the next one. Verified by ad-hoc script: `easy_readers p1 → p2 (empty) → picture_books p1` with limit respected.
- **Background execution (R2)**: `POST /admin/hydrate-all` is an `async def` endpoint that returns 202 immediately and schedules the synchronous hydration pipeline via `asyncio.create_task(asyncio.to_thread(_run_hydrate_all, task_id))`. Task references are kept in a module-level set with a `done_callback` discard (prevents GC mid-flight; self-cleans). Not Celery — ADR-004 defers Celery to question generation; this is a one-time load.
- **Fresh DB session in worker (S3-adjacent)**: the background worker creates its own `SessionLocal()` because the request-scoped session is closed as soon as the endpoint returns 202. Documented in `_run_hydrate_all` docstring.
- **Concurrency guard (S3)**: 409 Conflict when any task in `_tasks` has `status == "processing"`. Covers both hydrate-all and the existing (synchronous) hydrate path, since both write to the same store.
- **Per-grade status**: task store keeps a `grades` dict (grade → age/status/books_processed/error); `GET /admin/hydrate-all/{task_id}/status` returns per-grade breakdown plus aggregates. Partial failure semantics: a failing grade is marked `failed` with its error; the overall task is only `failed` if every grade failed.
- **Broad fallback**: `_subjects_for_age` appends `juvenile_fiction` (ages ≤ 12) or `young_adult_fiction` (ages ≥ 13) as a final subject if not already present, per the plan's mitigation.
- **`_get_existing_isbns` (S1)**: added comment noting full-table ISBN scan is acceptable <10K books per ADR-002; replace with `INSERT ... ON CONFLICT (isbn) DO NOTHING` if the catalog grows.
- **In-memory task store (S2)**: documented in `admin.py` — lost on restart, acceptable because hydrate-all is idempotent (ISBN dedup) and can be re-triggered.
- **`fetch_books_for_grade` (D1)**: NOT added — dead code otherwise, per plan review.
- **D2**: existing `POST /admin/hydrate` behavior now benefits from multi-subject iteration automatically; no code change needed.

### Deviations from Plan

- **Age 18 added to the subject map**: the plan table stops at age 17, but the existing `POST /admin/hydrate` validates `age` up to 18. Added `18: ["fantasy", "science_fiction", "young_adult_fiction"]` reusing only already-verified subjects to preserve the pre-existing age-18 coverage (previously `"fantasy"`).
- **`asyncio.to_thread` instead of raw `run_in_executor`**: equivalent mechanism, less boilerplate; satisfies the R2 requirement of `asyncio.create_task` + executor offloading.
- **Test client context manager**: acceptance tests now use `with TestClient(app) as client` (single long-lived portal). Without it, starlette 1.3.1 creates a per-request portal whose `loop.close()` → `default_executor.shutdown(wait=True)` blocks the request until background worker threads finish and cancels the background task — which broke the 409 concurrency test and added 10s stalls. The context-manager form matches uvicorn's long-lived loop. Fixture is file-local; no other test files affected.

### Verification

- `pytest tests/unit/test_services.py tests/acceptance/test_admin_api.py` — 34 passed (23 pre-existing + 11 new)
- `ruff check` + `ruff format --check` on the 3 changed files — clean
- `mypy app/api/admin.py app/services/hydration_service.py` — no issues
- OpenAPI schema confirms all 4 admin routes registered
- Full `pytest tests/` — 26 failures are pre-existing repo test-pollution (identical failure set on clean baseline via `git stash`); my changes add 11 passing tests (39 → 50)

## Test Results

*Pending tester delegation.*

## Code Review

**Reviewer**: Lead Code Reviewer | **Date**: 2026-08-03
**Verdict**: **CONDITIONAL PASS** — implementation is correct, clean, and matches the approved plan; all verification claims were independently reproduced. Two gaps (T1, T2) should be fixed or explicitly tracked as follow-ups before operational close-out, plus several minor issues. No blockers found.

### Verified Claims (all reproduced)

| Claim | Result |
|-------|--------|
| `pytest tests/unit/test_services.py tests/acceptance/test_admin_api.py` → 34 passed | ✅ Reproduced (34 passed, 1 pre-existing starlette deprecation warning) |
| Full `pytest tests/` → 26 failures / 50 passed | ✅ Reproduced; baseline worktree at `006b67e~1` also shows 26 failed / 39 passed — failures are pre-existing, the change adds 11 passing tests and no regressions |
| `ruff check` + `ruff format --check` clean on 3 changed files | ✅ Reproduced |
| `mypy` clean on admin.py + hydration_service.py | ✅ Reproduced |
| OpenAPI routes registered (hydrate, hydrate-all, 2 status endpoints) | ✅ Confirmed by route inspection |

### Findings

#### 🔴 Critical
None.

#### 🟡 Major

- **T1 — Core new logic has zero direct test coverage** (`backend/app/services/hydration_service.py`, `backend/tests/`).
  The heart of the R1 fix — multi-subject iteration in `fetch_top_books_for_age`, per-subject pagination reset, subject-exhaustion fallthrough, and `_subjects_for_age` fallback appending — is exercised by **no** test. Existing unit tests mock a single OpenLibrary response (single subject); the new acceptance tests monkeypatch `fetch_top_books_for_age` entirely, so they verify the endpoint plumbing but never the subject-iteration behavior. Per ADR-005, add unit tests for: (a) first subject exhausted → falls through to second subject; (b) limit spread across multiple subjects; (c) pagination resets to page 1 per subject; (d) `_subjects_for_age` appends the broad fallback only when absent (ages 6 and 12 where the fallback is already primary must not duplicate); (e) dedup-heavy pages terminate early.

- **T2 — Worker crash leaves task stuck in `processing` forever, wedging the admin API** (`backend/app/api/admin.py:186-217`, `_run_hydrate_all`).
  If `SessionLocal()` or `HydrationService.__init__` raises (e.g., DB unavailable at start), the exception propagates out of the worker before the per-grade try/except is entered. The task stays `status == "processing"` indefinitely, and because the 409 concurrency guard blocks on *any* processing task, **every future `POST /hydrate-all` returns 409 until process restart** (reproduced: worker crash → status endpoint returns 200/"processing"; subsequent hydrate-all → 409). Additionally, the exception is silently dropped by the `done_callback` (`_background_tasks.discard`) — it is never retrieved or logged ("Task exception was never retrieved"). Fix: wrap the worker body (after task lookup) in try/except, mark the task `failed` with the error, and log from the callback or retrieve the exception.

#### 🟢 Minor

- **M1 — `GET /hydrate-all/{task_id}/status` with a sync-`/hydrate` task id → unhandled `KeyError: 'grades'` → 500** (`backend/app/api/admin.py:292`). Reproduced. The two status endpoints share one in-memory task store but each assumes its own shape. Return 404 (or 400 "not a hydrate-all task") when `"grades"` is absent. The reverse direction (hydrate-all task queried via `/hydrate/{id}/status`) works because the response model only reads common keys.

- **M2 — Partial-failure accounting undercounts** (`hydration_service.py` `fetch_top_books_for_age` + `admin.py` `_run_hydrate_all`). If a grade fails mid-fetch (network error on page 3), books already stored to the DB for that grade are not reflected in `books_processed` (grade entry stays 0). Cosmetic for a one-time load, but the status output would disagree with `SELECT count(*)` per age. Consider capturing partial counts from the raised exception or accepting the discrepancy with a comment.

- **M3 — Dedup-heavy pages are scanned to exhaustion** (`hydration_service.py:136-148`). The inner loop only breaks on an empty `docs` page; a page full of already-stored ISBNs (common for grades sharing `young_adult_fiction` / `juvenile_fiction` primaries) pages through all 10 pages without early exit. Not a correctness bug — bounded (≤10 pages/subject) — just wasted API calls. Break when a page yields 0 *new* books.

- **M4 — `_tasks` never pruned** (`admin.py`). Completed/failed tasks accumulate for the process lifetime. Acceptable for a one-time load (S2 documented), but the store will grow without bound across repeated runs. Add a cap/TTL or prune-on-read for hygiene.

- **M5 — `docs/API_DESIGN.md` not updated** with the new `POST /admin/hydrate-all` and `GET /admin/hydrate-all/{task_id}/status` contracts, despite the plan citing API_DESIGN.md as the admin endpoint contract. Document the endpoints (request/response schemas, 409 semantics, 202 background behavior).

- **M6 — Commit-per-book** in `_store_book` (`hydration_service.py:209-213`): 100 commits + refreshes per grade, ~1,200 total. Pre-existing pattern; fine at this scale (ADR-002), but a single flush+commit per subject page would cut ~1,000 round-trips for free. Optional.

- **M7 — ISBN-10 check digits ending in "X" are discarded** by `_extract_isbn` (`clean.isdigit()`); pre-existing. Minor metadata loss, not a correctness regression.

### Adherence to Plan / Deviations

- ✅ `OPENLIBRARY_SUBJECTS` → `dict[int, list[str]]` with the 26 verified subjects — matches plan table exactly.
- ✅ `GRADE_AGE_MAP` (1→6 … 12→17) matches plan.
- ✅ Multi-subject fetch with per-subject pagination reset and exhausted-subject fallthrough.
- ✅ Broad-subject fallback appended per plan mitigation (`juvenile_fiction` ≤12, `young_adult_fiction` ≥13, deduped against existing list).
- ✅ `HydrateAllRequest` with `ge/le` bounds + `end_grade >= start_grade` model validator (correct pydantic v2 `model_validator(mode="after")` idiom).
- ✅ R2 blocker resolved: `async def` endpoint → 202 immediately → `asyncio.create_task(asyncio.to_thread(_run_hydrate_all, task_id))` with strong-ref set + `done_callback` discard. Correct pattern; connection never held for the 30–60s job.
- ✅ S3 blocker resolved: 409 guard covers both hydrate-all and the synchronous hydrate path (sync path holds `processing` while running).
- ✅ Fresh `SessionLocal()` in the worker thread, documented in the docstring (correct — request-scoped session dies with the 202).
- ✅ Per-grade status with partial-failure semantics (task `failed` only if every grade failed); S1 comment added; S2 limitation documented; D1 (`fetch_books_for_grade`) correctly omitted as dead code.
- ✅ Documented deviations are all reasonable: age 18 added to the map (preserves pre-existing coverage, only verified subjects reused); `asyncio.to_thread` over `run_in_executor` (equivalent, less boilerplate); TestClient context-manager fixture with a well-explained starlette portal rationale.

### Test Coverage Assessment

- ✅ Strong endpoint-level acceptance coverage: auth (401/422), defaults (1–12, 100/grade), inverted range, out-of-bounds bounds, immediate 202, per-grade breakdown + aggregates, 409 concurrency (using a blocking fetch + threading.Event — clever and deterministic), 400/404 for status lookups.
- ⚠️ Gaps: T1 (service-level multi-subject logic) and T2-adjacent (worker-init crash, all-grades-fail → task `failed` path, partial failure where one grade fails and the task stays `completed` with errors surfaced — the per-grade `error` field is asserted only as `None` in the happy path). The all-grades-fail branch (`total == 0 and errors`) and the grade-failure branch have no tests.

### Edge Cases & Error Handling

- `limit` arithmetic (`min(50, limit - len(stored))`) is safe: the while condition guarantees ≥1.
- Subject names with apostrophes (`children's_stories`) are URL-encoded by httpx automatically.
- Cross-grade dedup works because `_get_existing_isbns()` is re-queried per grade call (per plan).
- Age 18 reachable only via the legacy `/hydrate` endpoint; `GRADE_AGE_MAP` output (6–17) is fully covered by the subject map.
- Residual: `_tasks` cross-thread mutation relies on CPython GIL atomicity for individual dict ops — safe in practice, worth a one-line comment. Multi-worker uvicorn would duplicate the guard per-process (cross-worker double-hydration possible, mitigated by ISBN dedup).

### ✅ Praise

- The 409-concurrency acceptance test (blocking fetch + threading.Event) is a model of deterministic async testing.
- The TestClient context-manager discovery (starlette per-request portal shutdown cancelling background tasks) is a subtle, well-documented fix that would have cost hours of flaky-test debugging.
- `_subjects_for_age` fallback dedup logic (avoiding a duplicate primary) shows careful attention to the plan's mitigation detail.
- Clean separation: service stays API-agnostic; background execution, task bookkeeping, and per-grade status live in the router layer.
- All plan-review findings (R1, R2, S1–S3, D1–D3) are addressed or explicitly dispositioned in the implementation notes.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Code review findings written to issues/book-quiz-si8.md under '## Code Review': 0 critical, 2 major (T1: multi-subject fetch logic untested; T2: worker-init crash leaves task stuck 'processing' blocking all future hydrate-all with 409 — both reproduced), 7 minor, each with file paths, line refs, severity, and concrete fixes; verification claims (34 tests, ruff, mypy, baseline 26 failures) independently reproduced."
    }
  ],
  "changedFiles": [
    "backend/app/services/hydration_service.py",
    "backend/app/api/admin.py",
    "backend/tests/acceptance/test_admin_api.py",
    "issues/book-quiz-si8.md"
  ],
  "testsAddedOrUpdated": [
    "backend/tests/acceptance/test_admin_api.py (11 new tests: TestHydrateAllEndpoint x7, TestHydrateAllStatusEndpoint x4)"
  ],
  "commandsRun": [
    {
      "command": "pytest tests/unit/test_services.py tests/acceptance/test_admin_api.py",
      "result": "passed",
      "summary": "34 passed (23 pre-existing + 11 new), 1 starlette deprecation warning"
    },
    {
      "command": "pytest tests/",
      "result": "failed",
      "summary": "26 failed / 50 passed — identical failure set reproduced on baseline worktree at 006b67e~1 (26 failed / 39 passed); all 26 failures are pre-existing repo test-pollution, no regressions from this change"
    },
    {
      "command": "ruff check && ruff format --check (3 changed files)",
      "result": "passed",
      "summary": "All checks passed; 3 files already formatted"
    },
    {
      "command": "mypy app/api/admin.py app/services/hydration_service.py",
      "result": "passed",
      "summary": "Success: no issues found in 2 source files"
    },
    {
      "command": "ad-hoc repro: GET /hydrate-all/{sync-task-id}/status",
      "result": "failed",
      "summary": "Confirmed unhandled KeyError 'grades' -> 500 (finding M1)"
    },
    {
      "command": "ad-hoc repro: SessionLocal raises in worker",
      "result": "failed",
      "summary": "Confirmed task stuck at 'processing' forever; subsequent hydrate-all returns 409 (finding T2)"
    }
  ],
  "validationOutput": [
    "34/34 targeted tests pass; full suite 50 passed/26 failed with identical pre-existing failure set on baseline; ruff + mypy clean; both suspected edge cases (wrong-status-endpoint KeyError, worker-crash stuck task) empirically reproduced"
  ],
  "residualRisks": [
    "End-to-end hydration (~1,200 books against live OpenLibrary + PostgreSQL) not executed during code review — runtime verification remains pending per 'Test Results' section; subject slugs were curl-verified at plan-review stage (R1) but the final DB count per grade is unverified",
    "T1: multi-subject fetch logic (subject fallthrough, pagination reset, limit spread) has no direct unit tests — regression risk on the core R1 fix",
    "T2: a worker-start failure (e.g., DB down at trigger time) permanently wedges POST /hydrate-all with 409 until restart",
    "In-memory _tasks store: lost on restart (documented, idempotent) and never pruned — unbounded growth over repeated runs",
    "Cross-thread mutation of _tasks relies on CPython GIL atomicity; multi-worker uvicorn would bypass the 409 guard across processes (mitigated by ISBN dedup)"
  ],
  "noStagedFiles": true,
  "diffSummary": "Expands OPENLIBRARY_SUBJECTS to dict[int, list[str]] with 26 verified subjects per grade level; adds GRADE_AGE_MAP; reworks fetch_top_books_for_age for multi-subject iteration with per-subject pagination and broad-subject fallback; adds async POST /admin/hydrate-all (202 + asyncio.to_thread worker, 409 concurrency guard, per-grade status tracking) and GET /admin/hydrate-all/{id}/status; adds 11 acceptance tests; documents ADR/scale notes",
  "reviewFindings": [
    "major: backend/app/services/hydration_service.py - multi-subject fetch logic has zero direct test coverage (acceptance tests monkeypatch fetch_top_books_for_age); add unit tests for subject fallthrough, pagination reset, fallback append, dedup-heavy pages",
    "major: backend/app/api/admin.py:_run_hydrate_all - exception before per-grade try (SessionLocal/HydrationService init) leaves task 'processing' forever; 409 guard then blocks all future hydrate-all calls until restart; exception also never retrieved/logged in done_callback",
    "minor: backend/app/api/admin.py:292 - GET /hydrate-all/{id}/status with a sync-hydrate task id raises unhandled KeyError 'grades' -> 500; return 404 instead",
    "minor: hydration_service.py - partial-failure accounting: books stored before a mid-grade fetch error not reflected in books_processed",
    "minor: hydration_service.py - dedup-heavy pages page through all 10 pages without early exit on 0 new books",
    "minor: admin.py - _tasks never pruned (unbounded growth over repeated runs)",
    "minor: docs/API_DESIGN.md not updated with the two new hydrate-all endpoint contracts",
    "minor: hydration_service.py:_store_book - commit-per-book (~1,200 commits for full hydration); batch per page for free",
    "minor: hydration_service.py:_extract_isbn - ISBN-10 check digits ending in X discarded (pre-existing)",
    "verdict: CONDITIONAL PASS - no blockers; all plan-review findings (R1/R2/S1-S3/D1-D3) addressed; verification claims independently reproduced"
  ],
  "manualNotes": "Review only — no code changes made. Findings and verdict appended to issues/book-quiz-si8.md under '## Code Review'. T1/T2 majors should be fixed or tracked as follow-up beads before operational close-out; runtime hydration verification (~1,200 books in PostgreSQL) is still outstanding per the issue's Test Results section."
}
```

## Security Audit

**Auditor**: Senior Security Auditor | **Date**: 2026-08-03
**Scope**: `backend/app/services/hydration_service.py`, `backend/app/api/admin.py`, `backend/tests/acceptance/test_admin_api.py`
**Verdict**: 🟠 **CONDITIONAL PASS** — 3 High-severity findings that should be addressed before production deployment. No critical blockers.

---

### 🔴 Critical Findings (Blockers)
*None identified.*

---

### 🟠 High Severity

- **H1: Error Information Leakage via Task Status Endpoints**
  - **Location**: `backend/app/api/admin.py:128`, `backend/app/api/admin.py:226`
  - **Finding**: Both `trigger_hydration` (line 128) and `_run_hydrate_all` (line 226) capture raw `str(e)` from caught exceptions and store them in `_tasks`, which is served verbatim to any caller with the admin key via `GET /admin/hydrate/{task_id}/status` and `GET /admin/hydrate-all/{task_id}/status`. If a database connection fails, `str(e)` may include the full `DATABASE_URL` with embedded credentials (e.g., `postgresql://bookquiz:bookquiz_dev@localhost:5432/bookquiz`). Likewise, httpx or OpenLibrary errors may leak internal network paths, stack traces, or API internals.
  - **Impact**: An attacker with the admin key (or anyone who can guess a valid task UUID) can extract database credentials, internal network topology, or stack traces that aid further exploitation.
  - **Remediation**: Sanitize error messages stored in `_tasks` — capture only a generic category (e.g., `"database_error"`, `"openlibrary_api_error"`) and log the full `repr(e)` server-side via `logger.exception(...)`. Never store raw exception strings in user-visible task state. Alternatively, return only an opaque `error_code` and keep details in secure server logs.

- **H2: Race Condition in In-Memory Task Store (No Synchronization)**
  - **Location**: `backend/app/api/admin.py:19-20` (`_tasks` dict, `_background_tasks` set), `admin.py:169-232` (`_run_hydrate_all`), `admin.py:240-262` (`get_hydration_status`), `admin.py:268-300` (`get_hydrate_all_status`)
  - **Finding**: The module-level `_tasks` dict is accessed concurrently from two execution contexts: (1) the asyncio event loop (status endpoints via FastAPI route handlers, which are synchronous `def` but run in the event loop's threadpool), and (2) a worker thread spawned by `asyncio.to_thread()` in `trigger_hydrate_all`. While CPython's GIL makes individual dict get/set operations atomic, compound read-modify-write sequences are not. Specifically: the status endpoint iterates `task["grades"].values()` while `_run_hydrate_all` is mutating nested dict entries (`grade_entry["status"] = "processing"`, `grade_entry["books_processed"] = len(books)`). This can cause the status endpoint to see an inconsistent snapshot (e.g., `status == "completed"` but `books_processed == 0`). Additionally, `_background_tasks` is mutated from the done callback which runs in the event loop — simultaneous `discard` and `add` on a `set` can theoretically corrupt it if the GIL is released during a rehash.
  - **Impact**: Status polls may return inconsistent per-grade data (non-exploitable but breaks API contract). In extreme cases, a `RuntimeError: dictionary changed size during iteration` could crash a status request. The concurrency guard (409 check) on line 149-153 reads `_tasks.values()` under iteration while another thread could be modifying it — a TOCTOU window exists.
  - **Remediation**: Use `threading.Lock()` to guard all `_tasks` reads and writes. Wrap the status endpoint's dict reads and the background worker's writes with `with _tasks_lock:`. For the 409 concurrency check, hold the lock while iterating.

- **H3: Missing `Cache-Control: no-store` on Admin Status Endpoints**
  - **Location**: `backend/app/main.py:98-100` (security-headers middleware)
  - **Finding**: The security-headers middleware only adds `Cache-Control: no-store` for paths starting with `/api/v1/auth`. Admin endpoints (`/api/v1/admin/hydrate/*/status`, `/api/v1/admin/hydrate-all/*/status`) return task status including potentially sensitive metadata (per-grade book counts, error messages) but do not set cache-prevention headers. A shared proxy cache or browser back-button could serve stale task data to a different user.
  - **Impact**: Task status data (book counts, per-grade breakdown, error details) could be cached by intermediaries and served to unauthorized parties.
  - **Remediation**: Extend the cache-control condition in `main.py` to include `/api/v1/admin` paths, or add a response-class/route-level decorator on admin status endpoints that sets `Cache-Control: no-store`.

---

### 🟡 Medium Severity

- **M1: Shared Admin Key — No RBAC, No Audit Trail**
  - **Location**: `backend/app/api/admin.py:31-42`
  - **Finding**: The admin API uses a single shared secret (`X-Admin-Key` header) with no concept of individual admin identities, role-based access control, or audit logging. There is no record of *who* triggered a hydration job (only that a valid key was supplied). If the admin key is compromised, the attacker gains unrestricted access to all admin operations with no traceability.
  - **Impact**: No attribution for admin actions; single point of failure for access control; no way to rotate keys without downtime.
  - **Remediation**: Acceptable for this iteration (single-operator, one-time data load). Before production, consider: (a) logging the source IP and timestamp of admin actions, (b) supporting multiple API keys with individual revocation, or (c) integrating with the existing JWT auth system and adding an `admin` role to user accounts.

- **M2: Admin Key Comparison Susceptible to Timing Side-Channel**
  - **Location**: `backend/app/api/admin.py:40` — `x_admin_key != settings.admin_api_key`
  - **Finding**: Python's `!=` on strings short-circuits on the first differing byte, making the comparison time proportional to the length of the common prefix. Over many requests, an attacker can brute-force the admin key one character at a time by measuring response latency.
  - **Impact**: In theory, an attacker on the same network segment could extract the admin key. In practice, network jitter over WAN makes this attack noisy, but it remains a cryptographic best-practice concern.
  - **Remediation**: Use `hmac.compare_digest(x_admin_key, settings.admin_api_key)` or `secrets.compare_digest(...)` for constant-time comparison. Low effort, high security hygiene.

- **M3: No Timeout on Background Hydration Task**
  - **Location**: `backend/app/api/admin.py:157` — `asyncio.create_task(asyncio.to_thread(_run_hydrate_all, task_id))`
  - **Finding**: The background worker created via `asyncio.to_thread` has no timeout. If `_run_hydrate_all` hangs (e.g., network partition during an httpx call with a 30s timeout that never fires, or an infinite loop from a malformed OpenLibrary response), the task remains "processing" forever with no way to cancel it. The task reference is held in `_background_tasks` and never cleaned up until the done callback fires — which it never will if the thread hangs.
  - **Impact**: Resource leak (stuck thread). The 409 concurrency guard permanently blocks further hydration attempts.
  - **Remediation**: Add a `threading.Event` or `asyncio.Event` that signals cancellation. Wrap `_run_hydrate_all` with a maximum wall-clock timeout (e.g., 5 minutes). On timeout, set task status to `failed` with `error: "timeout"`.

- **M4: Per-Book Database Commits — No Transactional Atomicity per Grade**
  - **Location**: `backend/app/services/hydration_service.py:150-152` (`_store_book` calls `self.db.commit()` per book)
  - **Finding**: Each book is committed in its own transaction via `self.db.commit()` inside `_store_book`. If a hydration run for a grade fails after storing 50 of 100 books, those 50 books persist but the task reports `grade status: failed` with `books_processed: 0` (since `len(books)` captures only the successful return). This creates a mismatch between what's actually in the database and what the task status reports.
  - **Impact**: Data consistency gap — a failed grade may have partially stored books that aren't reflected in the task status. A re-run of the same grade would skip those books (ISBN dedup) and store only the remaining ones, which is actually correct behavior, but the status reporting is misleading.
  - **Remediation**: Either (a) accumulate books in a list and commit once at the end with `self.db.commit()` (providing per-grade atomicity), or (b) update `books_processed` incrementally even on partial success. Option (a) is preferable.

---

### 🟢 Low Severity / Recommendations

- **L1: Unbounded In-Memory Task Store Growth**
  - **Location**: `backend/app/api/admin.py:19` — `_tasks: dict[str, dict] = {}`
  - **Finding**: Completed/failed task entries are never evicted from `_tasks`. Over time, repeated hydration calls will cause unbounded memory growth. Mitigated by the fact that this is intended as a one-time load and the process restarts clear memory. Documented in implementation notes as acceptable limitation (S2).
  - **Remediation**: Add a TTL-based eviction (e.g., remove tasks older than 1 hour) or cap the dict at a maximum size.

- **L2: Database Connection String May Appear in Worker-Thread Error Logs**
  - **Location**: `backend/app/api/admin.py:225` — `logger.error(f"Hydration failed for grade {grade}: {e}")`
  - **Finding**: If `SessionLocal()` (line 214) fails to connect because the DB is unreachable, the SQLAlchemy error message includes the connection URL with embedded credentials. This goes to server logs only (not client-facing via the task status since the `except` block on line 222 catches `fetch_top_books_for_age` errors, not session-creation errors). However, if logs are aggregated to a centralized system with broader access, credentials could leak.
  - **Remediation**: Wrap `SessionLocal()` in a try/except and log a sanitized message (`"Database connection failed"`) rather than letting the raw exception propagate.

- **L3: OpenLibrary Subject Strings Are Hardcoded and Safe**
  - **Location**: `backend/app/services/hydration_service.py:25-54` (`OPENLIBRARY_SUBJECTS`), `hydration_service.py:125` (httpx `params` usage)
  - **Finding**: All subject values are hardcoded string constants. They are passed to `httpx.Client.get(params={"subject": subject, ...})`, which properly URL-encodes values. No injection risk. ✅ Verified clean.

- **L4: No SSRF Risk — OpenLibrary URL Is Hardcoded**
  - **Location**: `backend/app/services/hydration_service.py:88` — `OPENLIBRARY_SEARCH = "https://openlibrary.org/search.json"`
  - **Finding**: The external URL is a module-level constant, not user-controllable. No SSRF vector. ✅ Verified clean.

---

### ✅ Clean Areas (Passed Inspection)

| Area | Notes |
|------|-------|
| **Authentication middleware** (`admin.py:31-42`) | `_verify_admin_key` correctly returns 501 when `admin_api_key` is unconfigured and 401 on mismatch. No bypass vector found. |
| **Input validation** (`admin.py:48-74`) | Pydantic models enforce `age` (6-18), `limit` (1-500), `start_grade`/`end_grade` (1-12), `books_per_grade` (1-500). `model_validator` enforces `end_grade >= start_grade`. All edge cases covered. |
| **UUID validation** (`admin.py:180-186`, `admin.py:273-278`) | Task IDs validated via `uuid.UUID()` before dictionary lookup. Invalid UUIDs return 400, not 500. |
| **Generic exception handler** (`main.py:131-142`) | Differentiates debug vs production. In production, clients see only `{"detail": "An unexpected error occurred."}` — no stack traces or class names. |
| **Security headers** (`main.py:87-100`) | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, conditional HSTS. Good coverage for non-admin paths. |
| **Rate limiting** (`main.py:81-86`) | SlowAPI middleware active. Auth endpoints have specific limits (5/hour register, 5/minute login, 10/minute refresh). Global default of 60/minute. |
| **Password hashing** (`auth_service.py`) | bcrypt with per-password salts via `gensalt()`. No hardcoded secrets. |
| **JWT implementation** (`auth_service.py`) | `jti` claim for unique token identification, `type` claim to distinguish access/refresh, `sub` claim for user ID. `expected_type` enforcement prevents refresh-token-for-access swap. |
| **Database session hygiene** (`admin.py:214, 232`) | `_run_hydrate_all` creates a fresh `SessionLocal()` and closes it in `finally`. No request-scoped session leak into background thread. |
| **No hardcoded secrets** | Grep for API keys, passwords, tokens in `app/` returned zero hits. All secrets read from environment via `pydantic-settings`. |
| **Admin key not logged** | Request-logging middleware (`main.py:103-118`) logs method/path/status/elapsed only — no headers. Admin key stays out of access logs. |

---

### 📦 Dependency Status (Quick Scan)

| Package | Version | Known Concerns |
|---------|---------|---------------|
| `fastapi` | 0.141.1 | Latest patch; no critical CVEs. |
| `python-jose` | 3.5.0 | ⚠️ **Unmaintained** since 2021. Consider migrating to `PyJWT` (actively maintained) or `authlib`. No known exploitable CVEs in 3.5.0, but no security patches will be issued. |
| `bcrypt` | 5.0.0 | Latest stable; clean. |
| `httpx` | 0.28.1 | Slightly behind latest (0.28.x is stable). No critical CVEs. |
| `sqlalchemy` | 2.0.51 | Recent; no known issues. |
| `slowapi` | 0.1.9 | Lightweight; no known issues. |
| `celery` | 5.4.0 | Stable; no critical CVEs in this version. |
| `starlette` | (transitive via FastAPI) | 1.3.1 per test notes — verify this is patched against CVE-2025-XXXX (path traversal in StaticFiles). Not used in this code path. |

---

### Summary Verdict

| Category | Count |
|----------|-------|
| Critical | 0 |
| High | 3 (H1, H2, H3) |
| Medium | 4 (M1, M2, M3, M4) |
| Low | 3 (L1, L2, L3) |
| Clean | 10 areas |

**Overall**: The implementation is well-structured with good security hygiene (no hardcoded secrets, proper input validation, auth enforcement, secure defaults). The three high-severity findings (error leakage, race condition, missing cache headers) are all fixable with targeted changes and do not represent fundamental design flaws. The `python-jose` deprecation is a medium-term concern. All findings are confined to the admin API surface, which is already behind an authentication gate. **CONDITIONAL PASS** — recommended for merge after H1 (error sanitization) is addressed; H2 and H3 can follow in a fast-follow PR.
