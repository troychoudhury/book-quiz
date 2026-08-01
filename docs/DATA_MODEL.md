# Book Quiz — Data Model

## Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│    User      │       │  QuizAttempt     │       │    Book      │
├──────────────┤       ├──────────────────┤       ├──────────────┤
│ id (PK)      │──┐    │ id (PK)          │    ┌──│ id (PK)      │
│ email        │  │    │ user_id (FK)     │────┘  │ title        │
│ password_hash│  │    │ book_id (FK)     │────┐  │ author       │
│ display_name │  └───▶│ started_at       │    │  │ isbn         │
│ created_at   │       │ completed_at     │    │  │ cover_url    │
│ is_active    │       │ score            │    │  │ age_range    │
└──────────────┘       │ total_questions  │    │  │ description  │
                       │ attempt_number   │    │  │ created_at   │
                       └────────┬─────────┘    │  └──────────────┘
                                │              │
                                │              │
                       ┌────────▼─────────┐    │
                       │  QuizAnswer      │    │
                       ├──────────────────┤    │
                       │ id (PK)          │    │
                       │ attempt_id (FK)  │    │
                       │ question_id (FK) │──┐ │
                       │ selected_choice  │  │ │
                       │ is_correct       │  │ │
                       │ answered_at      │  │ │
                       └──────────────────┘  │ │
                                             │ │
                       ┌──────────────────┐  │ │
                       │    Question      │◄─┘ │
                       ├──────────────────┤    │
                       │ id (PK)          │    │
                       │ book_id (FK)     │────┘
                       │ chapter          │
                       │ chapter_title    │
                       │ question_text    │
                       │ question_type    │
                       │ difficulty       │
                       │ created_at       │
                       └────────┬─────────┘
                                │
                       ┌────────▼─────────┐
                       │    Choice        │
                       ├──────────────────┤
                       │ id (PK)          │
                       │ question_id (FK) │
                       │ choice_text      │
                       │ is_correct       │
                       │ position         │
                       └──────────────────┘
```

## Table Definitions

### users
| Column         | Type         | Constraints            |
|----------------|--------------|------------------------|
| id             | UUID         | PK, default gen_random_uuid() |
| email          | VARCHAR(255) | UNIQUE, NOT NULL, indexed |
| password_hash  | VARCHAR(255) | NOT NULL               |
| display_name   | VARCHAR(100) | NOT NULL               |
| created_at     | TIMESTAMPTZ  | NOT NULL, default now()|
| is_active      | BOOLEAN      | NOT NULL, default true |

### books
| Column      | Type         | Constraints            |
|-------------|--------------|------------------------|
| id          | UUID         | PK                     |
| title       | VARCHAR(500) | NOT NULL, indexed      |
| author      | VARCHAR(300) | NOT NULL               |
| isbn        | VARCHAR(13)  | UNIQUE, indexed        |
| cover_url   | TEXT         |                        |
| age_range   | INT4RANGE    |                        |
| description | TEXT         |                        |
| created_at  | TIMESTAMPTZ  | NOT NULL               |

### questions
| Column         | Type         | Constraints            |
|----------------|--------------|------------------------|
| id             | UUID         | PK                     |
| book_id        | UUID         | FK → books.id, indexed |
| chapter        | INTEGER      | NOT NULL               |
| chapter_title  | VARCHAR(500) |                        |
| question_text  | TEXT         | NOT NULL               |
| question_type  | VARCHAR(20)  | 'multiple_choice' only |
| difficulty     | VARCHAR(10)  | 'easy','medium','hard' |
| created_at     | TIMESTAMPTZ  | NOT NULL               |

### choices
| Column       | Type         | Constraints               |
|--------------|--------------|---------------------------|
| id           | UUID         | PK                        |
| question_id  | UUID         | FK → questions.id, CASCADE|
| choice_text  | TEXT         | NOT NULL                  |
| is_correct   | BOOLEAN      | NOT NULL, default false   |
| position     | SMALLINT     | NOT NULL                  |

### quiz_attempts
| Column          | Type         | Constraints            |
|-----------------|--------------|------------------------|
| id              | UUID         | PK                     |
| user_id         | UUID         | FK → users.id, indexed |
| book_id         | UUID         | FK → books.id, indexed |
| started_at      | TIMESTAMPTZ  | NOT NULL               |
| completed_at    | TIMESTAMPTZ  |                        |
| score           | INTEGER      |                        |
| total_questions | INTEGER      | NOT NULL, default 10   |
| attempt_number  | INTEGER      | NOT NULL               |

### quiz_answers
| Column          | Type         | Constraints                    |
|-----------------|--------------|--------------------------------|
| id              | UUID         | PK                             |
| attempt_id      | UUID         | FK → quiz_attempts.id, CASCADE |
| question_id     | UUID         | FK → questions.id              |
| selected_choice | UUID         | FK → choices.id                |
| is_correct      | BOOLEAN      | NOT NULL                       |
| answered_at     | TIMESTAMPTZ  | NOT NULL                       |

## Indexes

```sql
-- Book search
CREATE INDEX idx_books_title_trgm ON books USING gin (title gin_trgm_ops);
CREATE INDEX idx_books_isbn ON books (isbn);

-- Quiz deduplication
CREATE UNIQUE INDEX idx_unique_attempt ON quiz_attempts (user_id, book_id, attempt_number);

-- Performance
CREATE INDEX idx_questions_book_chapter ON questions (book_id, chapter);
CREATE INDEX idx_quiz_answers_attempt ON quiz_answers (attempt_id);
```
