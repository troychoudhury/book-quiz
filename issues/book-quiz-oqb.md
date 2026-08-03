# Implement user profile API endpoint

**Bead**: book-quiz-oqb | **Status**: closed

## Description

GET /users/me/profile returns all books user has attempted with scores, attempts, and remaining questions. GET /users/me/books/{id}/progress returns detailed progress for a specific book.

## Agent Log

| Date | Agent | Action | Summary |
|------|-------|--------|----------|
| 2026-08-01T04:50:02Z | system | created | Issue filed |
| 2026-08-03 | tech-lead | claim | Claimed for implementation |
| 2026-08-03 | tech-lead | implement | Added missing fields (cover_url, remaining_questions, can_retake) + 9 acceptance tests |

## Architecture Plan

The profile API in `backend/app/api/profile.py` was partially implemented. The following fields from the API_DESIGN spec were missing:
- `cover_url` from BookProgress
- `remaining_questions` from BookProgress and book progress response
- `can_retake` from book progress response
- `total_questions` from book progress response
- `attempts_completed` from book progress response

## Plan Review

**Verdict**: ✅ **PASS** — Gap is clear, changes are minimal additions.

## Implementation Notes

**Engineer**: tech-lead
**Date**: 2026-08-03

### Changes Made

1. **`backend/app/api/profile.py`**: Added `cover_url` and `remaining_questions` to `BookProgress` model. Updated `get_profile` to calculate `remaining_questions` and include `cover_url`. Updated `get_book_progress` to return `total_questions`, `remaining_questions`, `can_retake`, `cover_url`, `attempts_completed`.

2. **`backend/tests/acceptance/test_profile_api.py`**: 9 acceptance tests covering:
   - Profile: unauthenticated (401), user info, book progress with scores/remaining/cover, empty profile
   - Book progress: unauthenticated (401), detailed progress, invalid UUID, nonexistent book, unattempted book

## Test Results

**Verdict**: ✅ **ALL 9 PASSED**
