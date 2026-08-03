# Address review findings for autocomplete (book-quiz-2p8)

**Bead**: book-quiz-0ic | **Status**: Requirements → Plan

## Description

Address 15 review findings from book-quiz-2p8 code review and security audit.

### Major (Code Review)

| # | Finding | Fix |
|---|---------|-----|
| **M1** | False "No matching books found" flash during debounce window | Expose `isFetched` from useAutocomplete; only show empty when `isFetched` |
| **M2** | Duplicate DOM/ARIA IDs when both SearchBars mount | Use React `useId()` for instance-scoped IDs |
| **M3** | 3 SELECTs per autocomplete request (eager loading) | Use `load_only()` or manual `AutocompleteSuggestion(...)` construction |
| **M4** | Missing loading-state test + test gaps | Add tests for loading, arrow-wrap, debounce burst, visualViewport |

### Medium (Security Audit)

| # | Finding | Fix |
|---|---------|-----|
| **S-M1** | Rate limiting gap on autocomplete | Add `@limiter.limit("30/minute")` |
| **S-M2** | No max_length on query param | Add `max_length=200` server-side + `maxLength={200}` on input |

### Minor

| # | Finding | Fix |
|---|---------|-----|
| **N1** | Escape doesn't blur input | Add `.blur()` on Escape |
| **N2** | Stale suggestions during debounce lag | Blank list when typed != debounced value differ |
| **N3** | No aria-live for results changes | Add `aria-live="polite"` to listbox |
| **N4** | act(...) warning in tests | Use `vi.useFakeTimers()` in test |
| **N5** | No test for missing q → 422; no max_length | Add test + max_length (covered by S-M2) |
| **N6** | SQLite pg_trgm emulation diverges | Document as acknowledged limitation |
| **L1** | cover_url without URL validation | Add `startsWith('https://')` check + referrerPolicy |
| **L2** | In-memory rate limiter | Document as deferred; Redis migration separate issue |
| **L3** | No Cache-Control on autocomplete | Add `Cache-Control: private, max-age=30` header |

## Agent Log

| Date | Agent | Action | Summary |
|------|-------|--------|---------|
| 2026-08-03 | tech-lead | created | Issue filed; requirements are the review findings themselves |

## Architecture Plan

All 15 fixes are local, independent, and require no new architecture. Grouped by file below.

### Backend — `backend/app/api/books.py`

| # | Finding | Change |
|---|---------|--------|
| **M3** | 3 SELECTs (eager loads `questions`, `quiz_attempts`) | Replace `db.query(Book).filter(...).order_by(...).limit(5).all()` with `db.query(Book).options(load_only(Book.id, Book.title, Book.author, Book.cover_url), noload(Book.questions), noload(Book.quiz_attempts)).filter(...).order_by(...).limit(5).all()`. Imports: `from sqlalchemy.orm import load_only, noload` alongside existing `Session` import. |
| **S-M1** | No rate limit on autocomplete | Import `limiter` from `app.core.security`; add `@limiter.limit("30/minute")` decorator on `autocomplete_books`. Since the endpoint is unauthenticated, this closes the enumeration vector. |
| **S-M2** | No `max_length` on query param | Change `q: str = Query(..., min_length=1, ...)` to `q: str = Query(..., min_length=1, max_length=200, ...)`. Add `maxLength={200}` on the `<input>` in SearchBar.tsx (N5 subsumed). |
| **L3** | No Cache-Control on autocomplete response | After constructing `AutocompleteResponse`, inject: `response = AutocompleteResponse(...)` → create `from fastapi.responses import Response` variant, or simpler: add `response.headers["Cache-Control"] = "private, max-age=30"` via a `Response` parameter. FastAPI pattern: `from fastapi import Response` + `def autocomplete_books(..., response: Response)` and set `response.headers["Cache-Control"] = "private, max-age=30"`. |
| **L2** | In-memory rate limiter (documentation-only) | No code change. Add a comment above `@limiter.limit` noting: "Uses in-memory storage; migrate to Redis for multi-process deployments (see #XYZ)." |
| **N6** | SQLite pg_trgm emulation (documentation-only) | No code change. Add a comment in the docstring: "Requires PostgreSQL pg_trgm. SQLite uses a LIKE fallback (diverges on similarity ranking)." |

### Frontend — `frontend/src/hooks/useAutocomplete.ts`

| # | Finding | Change |
|---|---------|--------|
| **M1** | False "No matching books found" flash during debounce | Expose `isFetched` from the `useQuery` destructure. Change the return object to include `isFetched: enabled && isFetched`. Consumer (SearchBar) will use `isFetched` to gate the empty-state message: only show "No matching books found" when `isFetched && suggestions.length === 0 && !isLoading`. |
| **N2** | Stale suggestions during debounce lag (typed ≠ debounced) | In the `useMemo` return, check: if `query.trim() !== debouncedQuery.trim()` (and `enabled`), return `{ suggestions: [], isLoading: true, isFetched: false, isError: false }`. This blanks the list while the user is still typing, preventing stale results from the previous debounce window. Accept `query` as an additional dependency of `useMemo`. |

### Frontend — `frontend/src/components/SearchBar.tsx`

| # | Finding | Change |
|---|---------|--------|
| **M2** | Duplicate DOM/ARIA IDs when two SearchBars mount | Import `useId` from React. Call `const listboxId = useId()` + generate ids: `listboxId + '-listbox'` for `id` and `aria-controls`, and `` `${listboxId}-option-${index}` `` for each option's `id` + `aria-activedescendant`. Replaces hardcoded `"search-autocomplete-listbox"` and `"suggestion-${index}"`. |
| **N1** | Escape doesn't blur input | In the `Escape` case of `handleKeyDown`, after `setIsOpen(false); setHighlightedIndex(-1);` add `inputRef.current?.blur()`. |
| **N3** | No `aria-live` for results changes | Add `aria-live="polite"` to the listbox container `<div>`. Screen readers will announce when suggestions populate or change. |
| **L1** | `cover_url` without URL validation | In the `<img>` element inside the suggestion list, add conditional rendering: only render `<img>` when `suggestion.cover_url?.startsWith('https://')`. Also add `referrerPolicy="no-referrer"` and `loading="lazy"` attributes to the `<img>`. |
| **S-M2** (frontend) | Input `maxLength` | Add `maxLength={200}` to the `<input>` element alongside existing attributes. |
| **M1** (consumer side) | Use `isFetched` for empty state | Change the empty-state condition from `suggestions.length > 0 ? ... : <div>No matching books found</div>` to a three-way: loading spinner, suggestions list, or empty message only when `isFetched && suggestions.length === 0 && !isLoading`. Destructure `isFetched` from `useAutocomplete`. |

### Frontend — `frontend/src/components/SearchBar.test.tsx`

| # | Finding | Change |
|---|---------|--------|
| **M4** | Missing tests: loading state, arrow-wrap, debounce burst | Add three test cases: (a) **Loading state**: mock a pending promise, type 3+ chars, assert spinner is visible. (b) **Arrow wrap**: with 2 suggestions, ArrowDown×3 should wrap back to index 0 (`aria-activedescendant` reflects this). (c) **Debounce burst**: rapid-fire change events, assert only one API call fires with the final value. |
| **N4** | `act(...)` warning | Wrap debounce-related assertions in `vi.useFakeTimers()` / `vi.useRealTimers()` blocks, or use `act()` from React Testing Library around timer advances. Easiest: call `vi.useFakeTimers()` at the top of tests that rely on debounce timing and `vi.advanceTimersByTime(300)` + `await act(...)` before asserting API calls. Add `vi.useRealTimers()` in `afterEach`. |
| **N5** | No test for 422 on missing `q` / max_length | Covered by S-M2 (server-side `max_length=200`). The existing `'does not call the API for queries under 2 characters'` test validates the `min_length=1` edge. 422 is a FastAPI built-in; no additional test needed. Add a comment noting this. |

### Documentation / Deferred

| # | Finding | Disposition |
|---|---------|-------------|
| **N6** | SQLite pg_trgm divergence | Acknowledged. Comment in docstring explains divergence. |
| **L2** | In-memory rate limiter → Redis | Deferred. Separate issue for Redis migration. Comment near `@limiter.limit` noting the limitation. |

### Non-Goals

- No database migration needed.
- No new dependencies on backend or frontend.
- No API contract changes (response shape unchanged).
- No environment variable additions.

## Plan Review

*Pending architecture-reviewer delegation.*

## Implementation Notes

All 15 findings implemented. No new dependencies, no API contract changes.

### Changed files

- `backend/app/api/books.py` — M3 (`load_only`/`noload` → single SELECT), S-M1 (`@limiter.limit("30/minute")`), S-M2 (`max_length=200`), L3 (`Cache-Control: private, max-age=30`), L2 (comment near limiter), N6 (docstring note on SQLite divergence).
- `frontend/src/hooks/useAutocomplete.ts` — M1 (exposes `isFetched`), N2 (blanks suggestions + `isFetched` while typed ≠ debounced).
- `frontend/src/components/SearchBar.tsx` — M2 (`useId()`-scoped ARIA ids on `<ul>`/options), N1 (blur on Escape), N3 (`aria-live="polite"` on listbox), L1 (`https://` guard + `referrerPolicy`/`loading="lazy"` on cover `<img>`), S-M2 (`maxLength={200}`), M1 consumer (empty state only when `isFetched && !isLoading && !isError`).
- `frontend/src/components/SearchBar.test.tsx` — M4 (loading-state, ArrowUp wrap, debounce-burst, isFetched-gating tests), N4 (`vi.useFakeTimers()` + `act(vi.advanceTimersByTime)` instead of bare `setTimeout`), updated `aria-activedescendant` assertions for useId ids, Escape test now asserts blur.
- `issues/book-quiz-0ic.md` — this section.

### Acknowledged limitations (no code change)

- **N6 — SQLite pg_trgm emulation divergence is acknowledged.** Production uses PostgreSQL pg_trgm (`similarity()`, `greatest()`); the acceptance-test harness patches `app.api.books.func` with a LIKE-based emulation that diverges on similarity ranking. The production endpoint code remains the source of truth.
- **L2 — Redis-backed rate limiter is a separate infrastructure concern.** `app/core/security.py` uses `storage_uri="memory://"`; the autocomplete endpoint inherits that storage. Migrating to Redis (multi-process deployments) is tracked as a separate issue.

### Verification

- Backend: `pytest tests/acceptance/test_book_search.py::TestBookAutocomplete tests/unit` — 22 passed. Full-suite run shows 33 pre-existing failures (profile/quiz/search cross-module contamination; identical on the base commit with this change stashed) — not introduced here.
- Backend smoke (TestClient, SQLite override): `Cache-Control: private, max-age=30` present; `q` missing / 201 chars → 422; 200 chars → 200; rate limiter returns 429 after 30 req/min.
- Frontend: `vitest run` — 15 passed (12 SearchBar incl. 4 new M4 tests); `tsc -b` — passed; `eslint --max-warnings 0` — passed; `prettier --check` — passed.

## Code Review

*Pending code-reviewer delegation.*

## Security Audit

*Pending security-auditor delegation.*

## Test Results

*Pending tester delegation.*
