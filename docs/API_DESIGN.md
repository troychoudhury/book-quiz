# Book Quiz — API Design

Base URL: `/api/v1`

## Authentication

All `/api/v1/users/*` endpoints (except register/login) require:
```
Authorization: Bearer <access_token>
```

### POST /auth/register
```json
// Request
{ "email": "user@example.com", "password": "s3cur3P@ss!", "display_name": "Alice" }
// Response 201
{ "id": "uuid", "email": "user@example.com", "display_name": "Alice" }
```

### POST /auth/login
```json
// Request
{ "email": "user@example.com", "password": "s3cur3P@ss!" }
// Response 200
{ "access_token": "jwt...", "refresh_token": "jwt...", "token_type": "bearer" }
```

### POST /auth/refresh
```json
// Request
{ "refresh_token": "jwt..." }
// Response 200
{ "access_token": "new_jwt...", "refresh_token": "new_jwt..." }
```

## Books

### GET /books?q=harry+potter&page=1&size=20
```json
// Response 200
{
  "items": [
    {
      "id": "uuid", "title": "Harry Potter and the Sorcerer's Stone",
      "author": "J.K. Rowling", "isbn": "9780590353427",
      "cover_url": "https://...", "age_range": [8, 12],
      "question_count": 150
    }
  ],
  "total": 1, "page": 1, "size": 20
}
```

### GET /books/{book_id}
```json
// Response 200
{
  "id": "uuid", "title": "...", "author": "...", "isbn": "...",
  "cover_url": "...", "age_range": [8, 12], "description": "...",
  "chapters": 17, "total_questions": 150,
  "user_progress": { "attempts_completed": 2, "questions_answered": 20 }
}
```

## Quizzes

### POST /quizzes/start
```json
// Request (no auth — guest quiz)
{ "book_id": "uuid" }
// Request (authenticated)
{ "book_id": "uuid" }

// Response 201
{
  "attempt_id": "uuid",
  "questions": [
    {
      "id": "uuid", "question_number": 1,
      "question_text": "What is the main theme of Chapter 1?",
      "chapter": 1, "chapter_title": "The Boy Who Lived",
      "choices": [
        { "id": "uuid", "text": "Love conquers all", "position": 0 },
        { "id": "uuid", "text": "Power corrupts", "position": 1 },
        { "id": "uuid", "text": "Knowledge is power", "position": 2 },
        { "id": "uuid", "text": "Revenge is sweet", "position": 3 }
      ]
    }
    // ... 9 more questions
  ]
}
```

### POST /quizzes/{attempt_id}/answer
```json
// Request
{ "question_id": "uuid", "choice_id": "uuid" }
// Response 200
{ "is_correct": true, "correct_choice_id": "uuid", "question_number": 1 }
```

### POST /quizzes/{attempt_id}/complete
```json
// Request (guest — optionally provide email)
{ "email": "user@example.com" }
// Response 200
{
  "attempt_id": "uuid", "score": 8, "total": 10,
  "percentage": 80, "completed_at": "2025-01-01T00:00:00Z",
  "results": [
    { "question_id": "uuid", "question_text": "...",
      "selected_choice": "Love conquers all", "correct_choice": "Love conquers all",
      "is_correct": true, "chapter": 1 }
  ]
}
```

## User Profile

### GET /users/me/profile
```json
// Response 200
{
  "id": "uuid", "email": "user@example.com", "display_name": "Alice",
  "total_quizzes": 5, "total_questions_answered": 50,
  "books": [
    {
      "book_id": "uuid", "title": "Harry Potter...", "author": "...",
      "cover_url": "...", "attempts": [
        { "attempt_number": 1, "score": 7, "total": 10, "completed_at": "..." },
        { "attempt_number": 2, "score": 9, "total": 10, "completed_at": "..." }
      ],
      "best_score": 90, "total_questions_answered": 20,
      "remaining_questions": 130
    }
  ]
}
```

### GET /users/me/books/{book_id}/progress
```json
// Response 200
{
  "book_id": "uuid", "title": "...",
  "attempts_completed": 2, "total_questions_answered": 20,
  "total_questions": 150, "remaining_questions": 130,
  "can_retake": true,
  "attempts": [/* attempt history */]
}
```

## Admin / Background

### POST /admin/hydrate
```json
// Request (requires admin key)
{ "age": 10, "limit": 100 }
// Response 202
{ "task_id": "uuid", "status": "processing", "message": "Hydration job started" }
```

### GET /admin/hydrate/{task_id}/status
```json
// Response 200
{ "task_id": "uuid", "status": "completed", "books_processed": 100,
  "questions_generated": 1500, "errors": [] }
```
