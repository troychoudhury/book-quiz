# Implement quiz question generation pipeline for all books

**Bead**: book-quiz-0gr | **Status**: Closed

## Implementation Notes

**Engineer**: Tech Lead | **Date**: 2026-08-03

### Changed Files

1. `backend/app/services/question_generator.py` — Added `generate_for_book()` and `_build_book_prompt()` methods that work without chapter data
2. `backend/app/services/hydration_service.py` — Replaced `generate_questions_for_book()` stub with real implementation
3. `backend/app/api/admin.py` — Added generate-questions, generate-questions-all, and status endpoints

### Key Decisions

- **No chapter data needed**: AI uses its knowledge of the book from title + author + age range. Generates 10 questions as `chapter=0`.
- **Idempotent**: Skips books that already have questions
- **Graceful degradation**: Returns 0 questions with warning log if no API key
- **Background execution**: async 202 pattern matching hydrate-all

## Test Results

| Test | Result |
|------|--------|
| POST /admin/generate-questions | ✅ 202, task completes |
| Placeholder API key → 0 questions | ✅ Graceful |
| Backend tests (test_admin_api.py) | ✅ 20/20 pass |

## ⚠️ To generate real questions:

1. Set a real OpenAI API key in `.env`: `OPENAI_API_KEY=sk-your-real-key`
2. Restart backend
3. Test with 5 books:
```bash
curl -X POST http://localhost:8000/api/v1/admin/generate-questions-all \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_books": 5}'
```
4. Generate all 1,200 (~30 min, ~$5-10):
```bash
curl -X POST http://localhost:8000/api/v1/admin/generate-questions-all \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_books": 0}'
```
