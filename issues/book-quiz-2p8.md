# Add typeahead/autocomplete to book search box

**Bead**: book-quiz-2p8 | **Status**: Requirements

## Description

Add typeahead and autocomplete functionality to the book search box on the landing page and any other search surfaces.

### Expected Behavior
- As user types in the search box, suggestions appear below (typeahead)
- Suggestions show matching book titles and authors
- Selecting a suggestion navigates to that book or fills the search
- Debounced API calls to avoid excessive requests
- Works for both desktop and mobile

### Context
- Existing `GET /api/v1/books` supports fuzzy search with query parameter
- Landing page (book-quiz-9y1) has search bar implemented
- Frontend: React + Tailwind CSS
- Backend: FastAPI with pg_trgm search
- DB has 1,200 books across grades 1-12

## Agent Log

| Date | Agent | Action | Summary |
|------|-------|--------|---------|
| 2026-08-03 | tech-lead | created | Issue filed, moved to requirements |

## Requirements Clarification

**Clarified by**: Product Manager | **Date**: 2026-08-03

### Problem Statement

Users currently must type a full query and press Enter to see any results. There is no real-time feedback while typing, leading to:
- **Uncertainty**: "Is this book even in the system?"
- **Wasted effort**: User types full title only to find zero results
- **Slow discovery**: No way to browse by partial input

### Target Audience
All users who search for books — the primary interaction on the landing page.

### User Stories

- **US-1**: As a reader, I want to see matching book suggestions as I type, so that I can quickly find my book without typing the full title.
- **US-2**: As a reader, I want to see the author name in suggestions, so that I can distinguish books with similar titles.
- **US-3**: As a reader, I want to click a suggestion to go directly to the book detail page, so that I can start a quiz immediately.
- **US-4**: As a reader on mobile, I want the suggestion dropdown to be touch-friendly and not obscure the keyboard, so that I can easily select a book.

### Decisions on Key Questions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Endpoint for autocomplete? | **New dedicated endpoint**: `GET /api/v1/books/autocomplete?q=...` | Existing `/api/v1/books` runs a full COUNT query and returns pagination metadata — too heavy. New endpoint uses `LIMIT 5`, leverages pg_trgm `similarity()` ordering (DB already has `idx_books_title_trgm` GIN index), and returns a slim payload. |
| 2 | Data in suggestions? | **title + author + cover thumbnail + book id** | Title alone is ambiguous (many editions). Author disambiguates. Cover thumbnail aids visual recognition (already in Book model). ID is needed for navigation. |
| 3 | How many suggestions? | **5** | Standard for typeahead; balances utility with scanability. With 1,200 books, 5 is enough to capture the most relevant matches. |
| 4 | On-select behavior? | **Navigate directly to `/books/:id`** | User picking a specific book from a dropdown wants to see its detail page to start a quiz. Pressing Enter without selecting still triggers the existing search-results page flow. |
| 5 | Debounce timing? | **300ms** | Industry standard; balances responsiveness with server load. |
| 6 | "No results" state? | **Yes — show "No matching books found"** | Provides clear feedback instead of a confusing empty dropdown. |
| 7 | Accessibility? | **ARIA combobox pattern** (role="combobox", aria-expanded, aria-activedescendant, aria-autocomplete="list") + full keyboard navigation (arrow keys, Enter, Escape) | Required for screen-reader users and keyboard-only navigation. |

### Acceptance Criteria (Gherkin)

```gherkin
Feature: Book search autocomplete

  Scenario: Suggestions appear while typing
    Given I am on the landing page
    When I type "harry" in the search box and pause for 300ms
    Then I see up to 5 suggestions with title, author, and cover thumbnail
    And the suggestions are ordered by relevance

  Scenario: Minimum input length
    Given I am on the landing page
    When I type fewer than 2 characters in the search box
    Then no API call is made
    And no suggestion dropdown appears

  Scenario: Select a suggestion
    Given suggestions are visible for "harry potter"
    When I click the suggestion "Harry Potter and the Sorcerer's Stone"
    Then I am navigated to /books/{id} for that book

  Scenario: Keyboard navigation
    Given suggestions are visible for "harry"
    When I press ArrowDown twice and press Enter
    Then I am navigated to the book detail page for the 2nd suggestion

  Scenario: Escape closes suggestions
    Given suggestions are visible for "harry"
    When I press Escape
    Then the suggestion dropdown closes
    And the search box retains my typed text

  Scenario: No results
    Given I type "xyznonexistent" and pause for 300ms
    Then I see a message "No matching books found" in the dropdown

  Scenario: Press Enter without selecting
    Given suggestions are visible for "harry"
    When I do not highlight any suggestion and press Enter
    Then I am navigated to /search?q=harry (existing full search flow)

  Scenario: Both search surfaces (Landing + Header)
    Given I am on any page with the header search bar
    When I type in the header search bar
    Then autocomplete suggestions also appear there
    And on-select navigates to book detail

  Scenario: Loading state
    Given I type "harry" in the search box
    When the API call is in flight
    Then I see a subtle loading indicator at the bottom of the dropdown

  Scenario: API error handling
    Given the autocomplete API is unreachable
    When I type in the search box
    Then the dropdown silently fails (no suggestions shown)
    And my typing is not interrupted
```

### Autocomplete API Specification

```
GET /api/v1/books/autocomplete?q={query}

# Response 200
{
  "suggestions": [
    {
      "id": "uuid",
      "title": "Harry Potter and the Sorcerer's Stone",
      "author": "J.K. Rowling",
      "cover_url": "https://..."
    }
  ]
}
```

- Query parameter `q`: required, minimum 2 characters (return empty list if shorter)
- Response: array of up to 5 suggestions, ordered by `pg_trgm.similarity(title, query) DESC`
- No pagination, no count — this is a lightweight endpoint
- No authentication required
- Response time target: < 100ms p95

### Scope Boundaries

**In scope**:
- New `GET /api/v1/books/autocomplete` endpoint
- New `AutocompleteResponse` Pydantic schema
- Shared `<SearchBar />` component with autocomplete (used on both Landing and Header)
- Debounced input handling (300ms)
- Keyboard navigation (ArrowUp, ArrowDown, Enter, Escape)
- ARIA combobox accessibility
- "No results" empty state

**Out of scope** (for this issue):
- Replacing the existing full-search endpoint with pg_trgm (separate optimization)
- Caching autocomplete responses (premature for 1,200 book dataset)
- Fuzzy-correcting typos beyond what pg_trgm provides
- Search history or recent searches
- Highlighting matched text within suggestions (nice-to-have, separate PR)

### RICE Prioritization

| Factor | Score | Notes |
|--------|-------|-------|
| **Reach** | 8/10 | Every user touches search; it's the primary entry point |
| **Impact** | 7/10 | Significantly faster book discovery; reduces bounce |
| **Confidence** | 9/10 | Autocomplete is a proven, well-understood pattern |
| **Effort** | 5/10 | ~1 backend endpoint + ~1 shared frontend component |
| **RICE Score** | **100.8** | (8 × 7 × 9) / 5 |

### Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| pg_trgm similarity() is slow without proper index | Low | `idx_books_title_trgm` GIN index already exists; `similarity()` can leverage it with a recheck. Verify with EXPLAIN ANALYZE. |
| Excessive API calls if debounce fails | Low | Debounce at 300ms; skip calls for < 2 chars |
| Dropdown overlaps mobile keyboard | Medium | Position dropdown above input on mobile with `bottom: 100%`; test on iOS Safari + Chrome Android |

---

**Status**: `status_requirements_clarified` — Ready for architecture review.

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
