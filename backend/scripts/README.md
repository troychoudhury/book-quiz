# Series Hydration & Question Generation — Ops Guide

Data-ops tooling for the series-based book catalog load (book-quiz-ifq).
The production database holds ~6,200 books and ~150k+ AI-generated
questions — treat it as valuable, expensive-to-recreate data.

## How to run

```bash
# Prereqs: Cloud SQL proxy running, DATABASE_URL pointing at the socket,
# OPENAI_API_KEY / OPENAI_MODEL / OPENAI_BASE_URL from .env.production.

# Books (resumable via scripts/.hydrate_state.json)
python -m scripts.hydrate_series --dry-run   # preview, no writes
python -m scripts.hydrate_series              # real run

# Questions (resumable via scripts/.questions_state.json)
python -m scripts.generate_questions --workers 16
```

Both scripts are idempotent: books dedup by ISBN against the DB; questions
skip books that already have questions. Safe to rerun after a crash — only
the in-flight transaction is lost.

## Data preservation (production, Cloud SQL `book-quiz-db`)

Enabled as of 2026-08-09 (see beads book-quiz-ifq):

| Layer | Status |
|---|---|
| Automated daily backups | ✅ enabled, 07:00 UTC, 7 retained |
| Deletion protection | ✅ enabled (instance can't be dropped without explicit override) |
| Point-in-time recovery | ✅ enabled (logs retained 7 days; fields populate after first backup cycle) |
| Manual snapshot to GCS | ✅ `gs://book-quiz-db-backups/` (`gcloud sql export sql`) |
| Regeneration path | ✅ scripts + series lists committed in this repo |

### Restore procedure

```bash
# From the latest automated backup:
gcloud sql backups list --instance=book-quiz-db
gcloud sql backups restore <BACKUP_ID> --restore-instance=book-quiz-db

# Or from a GCS export:
gcloud sql import sql book-quiz-db gs://book-quiz-db-backups/manual-*.sql.gz

# Verify after restore:
#   books == expected count, questions == expected count,
#   every book has ≥1 question (except newly-added during a running load)
```

### Take a fresh manual snapshot

```bash
gcloud sql export sql book-quiz-db \
  gs://book-quiz-db-backups/manual-$(date +%Y%m%d-%H%M).sql.gz --database=bookquiz
```

### Regeneration path (if the DB were lost entirely)

1. `git clone` — the curated series lists and scripts are committed here.
2. Re-run `scripts/hydrate_series.py` → books back from OpenLibrary (ISBNs
   recorded in the old dump; rehydration dedups by ISBN).
3. Re-run `scripts/generate_questions.py` → questions back via DeepSeek.
   This is the expensive step (~12k API calls for the series load).

## Guardrails against accidental damage

- **No delete endpoints** in the admin API — data can only be added via
  hydration/generation; nothing in the app deletes books/questions.
- **Per-book transactional writes** — a crash mid-load loses at most one
  book's questions; the scripts resume from DB state, not memory.
- **`./dev db-reset` targets local dev only** (`dev.db`/test DBs), never
  production (production URL comes from `.env.production` / Cloud Run env).
- **Careful manual SQL** — the junk-row cleanup in this load used
  reviewed, pattern-matched deletes with a dry-run list printed first;
  keep that pattern for future data ops.
- **Never commit** the local `backups/` copies or `.env.production` —
  they contain production data/secrets (gitignored).
