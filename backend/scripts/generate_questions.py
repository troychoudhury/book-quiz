#!/usr/bin/env python3
"""Generate quiz questions for all books that don't have any yet.

Usage:
    python -m scripts.generate_questions                # default 4 workers
    python -m scripts.generate_questions --workers 8
    python -m scripts.generate_questions --limit 100    # cap this run

Resumable: books that already have questions are skipped (the service
itself checks) and a state file tracks books attempted. Safe to rerun.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models.book import Book  # noqa: E402
from app.services.hydration_service import HydrationService  # noqa: E402

STATE_FILE = Path(__file__).resolve().parent / ".questions_state.json"


def load_state() -> set[str]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_state(done: set[str]) -> None:
    STATE_FILE.write_text(json.dumps(sorted(done)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="max books this run")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL env var required", file=sys.stderr)
        sys.exit(1)

    settings = get_settings()
    if not settings.openai_api_key:
        print("OPENAI_API_KEY not configured — cannot generate questions", file=sys.stderr)
        sys.exit(1)
    print(
        f"Model: {settings.openai_model} | "
        f"base_url: {settings.openai_base_url or 'openai default'}"
    )

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)

    done = load_state()
    with Session() as s:
        rows = s.execute(
            text(
                "SELECT b.id, b.title, b.author FROM books b "
                "LEFT JOIN questions q ON q.book_id = b.id "
                "GROUP BY b.id HAVING count(q.id) = 0 ORDER BY b.created_at"
            )
        ).all()
    pending = [(str(r[0]), r[1], r[2]) for r in rows if str(r[0]) not in done]
    print(
        f"Books without questions: {len(rows)} "
        f"(skipping {len(rows) - len(pending)} already attempted)"
    )
    if args.limit:
        pending = pending[: args.limit]
    print(f"Processing {len(pending)} books with {args.workers} workers…")

    start = time.monotonic()
    processed = 0
    total_qs = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_gen, engine, bid, title, author): bid
            for bid, title, author in pending
        }
        for fut in as_completed(futures):
            bid = futures[fut]
            try:
                count = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [err] {bid}: {e}", flush=True)
                count = -1
            processed += 1
            if count > 0:
                # Only count as done when questions actually landed; a 0
                # (e.g. AI JSON parse failure) is retried on the next run.
                done.add(bid)
                total_qs += count
            elif count == 0:
                print(f"  [retry] {bid}: 0 questions generated", flush=True)
            if processed % 10 == 0 or processed == len(pending):
                elapsed = time.monotonic() - start
                rate = processed / elapsed if elapsed else 0
                eta = (len(pending) - processed) / rate if rate else 0
                print(
                    f"  {processed}/{len(pending)} | +{total_qs} questions | "
                    f"{rate:.2f} books/s | ETA {eta/60:.1f} min",
                    flush=True,
                )
            if processed % 25 == 0:
                save_state(done)

    save_state(done)
    print(
        f"\nDONE: {processed} books processed, {total_qs} questions in "
        f"{(time.monotonic()-start)/60:.1f} min"
    )


def _gen(engine, bid: str, title: str, author: str) -> int:
    """Generate questions for one book in its own session (thread-safe).

    Retries twice when the model returns no questions (e.g. malformed JSON)
    before giving up, so transient parse failures don't silently lose books.
    """
    Session = sessionmaker(bind=engine)
    for attempt in range(3):
        with Session() as s:
            service = HydrationService(s, openai_api_key=get_settings().openai_api_key)
            q = service.generate_questions_for_book(uuid.UUID(bid))
            s.commit()
        if q > 0:
            return q
        if attempt < 2:
            time.sleep(5 * (attempt + 1))
    return q


if __name__ == "__main__":
    main()
