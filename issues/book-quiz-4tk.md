# Fix autocomplete UX: scrollable results + no blink on keystroke

**Bead**: book-quiz-4tk | **Status**: Implement

## Problem

1. **Limit of 5**: Backend LIMIT 5 with no scroll — user wants all matches
2. **Blink on keystroke**: `isStale` blanking clears the list on every keystroke, creating jarring repaint

## Fix

1. Backend: `.limit(5)` → `.limit(50)`, update docstring
2. useAutocomplete: Remove `isStale` blanking — keep previous results during debounce. Show spinner alongside existing results instead of replacing them.
3. SearchBar: Add `max-h-64 overflow-y-auto` for scroll. Show loading indicator below existing results (not instead of them) during re-fetch.

## Agent Log

| Date | Agent | Action | Summary |
|------|-------|--------|---------|
| 2026-08-03 | tech-lead | created | User-reported UX issues |

## Implementation Notes

**Engineer**: Tech Lead | **Date**: 2026-08-03

### Changed Files

1. `backend/app/api/books.py` — `.limit(5)` → `.limit(50)`, docstring updated
2. `frontend/src/hooks/useAutocomplete.ts` — Removed `isStale` blanking; keep previous results visible; added `isPending` for initial spinner
3. `frontend/src/components/SearchBar.tsx` — Added `max-h-64 overflow-y-auto` scroll; spinner shows for initial load (`isLoading || isPending`); "Updating..." indicator below existing results during re-fetch; standalone "No matching books found" only after fetch resolves
4. `frontend/src/components/SearchBar.test.tsx` — No changes needed (tests pass as-is)
5. `backend/tests/acceptance/test_book_search.py` — Updated limit test from 5→50

### Behavior Changes

| Before | After |
|--------|-------|
| LIMIT 5, no scroll | LIMIT 50, `max-h-64 overflow-y-auto` scroll |
| List cleared to `[]` on every keystroke | Previous results persist, spinner alongside |
| `isStale` blanking | `isPending` flag for initial spinner only |

## Test Results

**Tester**: Tech Lead | **Date**: 2026-08-03

| Suite | Result |
|-------|--------|
| Frontend Vitest | 15/15 pass |
| Backend acceptance tests | 22/22 pass |
| Smoke: `?q=harry` | 50 suggestions returned |

### Verdict: ✅ Both UX issues resolved
