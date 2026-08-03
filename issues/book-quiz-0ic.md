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

*Pending architect delegation.*

## Plan Review

*Pending architecture-reviewer delegation.*

## Implementation Notes

*Pending engineer delegation.*

## Code Review

*Pending code-reviewer delegation.*

## Security Audit

*Pending security-auditor delegation.*

## Test Results

*Pending tester delegation.*
