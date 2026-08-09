#!/usr/bin/env python3
"""Hydrate books for curated children's book series (ages 6-12) into the DB.

Usage:
    python -m scripts.hydrate_series            # run against DATABASE_URL
    python -m scripts.hydrate_series --dry-run  # count without writing
    python -m scripts.hydrate_series --age 8    # only one age band

Data source: OpenLibrary search (q=series:"Name") — returns work-level docs
with title/author/isbn. Books are deduped by ISBN against existing rows and
within the run. Per-series atomic commits; a state file makes the run
resumable (re-running skips completed series).

Series lists: scripts/book_series.json (curated top series per age 6-12).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.book import Book  # noqa: E402
from app.models.base import Base  # noqa: E402

SERIES_FILE = Path(__file__).resolve().parent / "book_series.json"
STATE_FILE = Path(__file__).resolve().parent / ".hydrate_state.json"

# Keywords that indicate compilations / sets / foreign editions to skip.
SKIP_TITLE = re.compile(
    r"collection|box\s*set|boxset|gift\s*set|books\s*set|\d\s*book[s]?\s*set|"
    r"set\s*[-:]\s*\d|set\s+by\b|\d-\d\s*set|treasury|omnibus|\baudio\b|"
    r"chinese|kutulu\s*set|serisi|complete\s+series|complete\s+\d|"
    r"pez\s+candy|harmonica|pedagogy|parody|time\s+tunnel|french\s+edition|"
    r"bundle|trilogie|chroniques de narnia|asimov|emily\s+dickinson",
    re.IGNORECASE,
)
# Foreign-language editions carry non-ASCII titles — skip them.
NON_ASCII = re.compile(r"[^\x00-\x7F]")
MAX_BOOKS_PER_SERIES = 40
SERIES_SEARCH_LIMIT = 100


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"ages": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def ol_search(params: dict) -> dict:
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError("unreachable")


def series_works(series_name: str) -> list[dict]:
    """Return usable work-docs for a series (title, author, isbn).

    Two-tier lookup because OpenLibrary's series index is incomplete:
    1. ``q=series:"NAME"`` — works explicitly tagged with the series.
    2. ``q=title:"NAME"``  — works whose title contains the series name
       (e.g. "The Absent Author (A to Z Mysteries, #1)"), merged in and
       deduped by ISBN, series-tagged docs first.
    """
    docs = _search(f'series:"{series_name}"')
    title_docs = _search(f'title:"{series_name}"')
    name_l = series_name.lower()
    merged = list(docs)
    merged.extend(
        d for d in title_docs if name_l in (d.get("title") or "").lower()
    )

    seen_isbns: set[str] = set()
    out: list[dict] = []
    for doc in merged:
        title = (doc.get("title") or "").strip()
        if not title or NON_ASCII.search(title) or SKIP_TITLE.search(title):
            continue
        authors = doc.get("author_name") or []
        author = authors[0] if authors else "Unknown Author"
        isbn = _first_valid_isbn(doc.get("isbn", []))
        if not isbn or isbn in seen_isbns:
            continue
        seen_isbns.add(isbn)
        out.append(
            {
                "title": title[:500],
                "author": author[:300],
                "isbn": isbn,
                "first_publish_year": doc.get("first_publish_year"),
            }
        )
        if len(out) >= MAX_BOOKS_PER_SERIES:
            break
    return out


def _search(query: str) -> list[dict]:
    data = ol_search(
        {
            "q": query,
            "fields": "key,title,author_name,isbn,first_publish_year",
            "limit": SERIES_SEARCH_LIMIT,
        }
    )
    return data.get("docs", [])


def _first_valid_isbn(isbns: list) -> str | None:
    for raw in isbns:
        clean = raw.replace("-", "").replace(" ", "")
        if len(clean) in (10, 13) and clean.isdigit():
            return clean
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="count without writing")
    parser.add_argument("--age", type=int, help="only hydrate this age band")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL env var required (e.g. Cloud SQL socket URL)", file=sys.stderr)
        sys.exit(1)

    series_lists = json.loads(SERIES_FILE.read_text())
    ages = [str(a) for a in range(6, 13)]
    if args.age:
        ages = [str(args.age)]

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    state = load_state()

    # Load all existing ISBNs once — dedup against production.
    with Session() as s:
        existing = {row for (row,) in s.query(Book.isbn).filter(Book.isbn.isnot(None)).all()}
    print(f"Production ISBNs on disk: {len(existing)}")

    total_new = 0
    total_existing = 0
    total_series_processed = 0
    for age in ages:
        if age not in series_lists:
            continue
        age_new = 0
        for series in series_lists[age]:
            if state["ages"].get(age, {}).get(series):
                print(f"  [skip] age {age} · {series} (already done)")
                continue
            works = series_works(series)
            new_in_series = 0
            dup_in_series = 0
            if not args.dry_run:
                with Session() as s:
                    for w in works:
                        if w["isbn"] in existing:
                            dup_in_series += 1
                            continue
                        existing.add(w["isbn"])
                        s.add(
                            Book(
                                id=uuid.uuid4(),
                                title=w["title"],
                                author=w["author"],
                                isbn=w["isbn"],
                                age_range_lower=int(age),
                                age_range_upper=int(age) + 2,
                            )
                        )
                        new_in_series += 1
                    s.commit()
            else:
                for w in works:
                    if w["isbn"] in existing:
                        dup_in_series += 1
                    else:
                        existing.add(w["isbn"])
                        new_in_series += 1
            age_new += new_in_series
            total_new += new_in_series
            total_existing += dup_in_series
            total_series_processed += 1
            print(
                f"age {age} · {series:<40} series-books={len(works):>3} "
                f"new={new_in_series:>3} dup={dup_in_series:>3}"
            )
            if not args.dry_run:
                state.setdefault("ages", {}).setdefault(age, {})[series] = {
                    "new": new_in_series,
                    "dup": dup_in_series,
                }
                save_state(state)
            time.sleep(0.3)  # be polite to OpenLibrary

        print(f"== age {age}: +{age_new} new books")

    print(
        f"\nDONE ({'DRY RUN' if args.dry_run else 'executed'}): "
        f"{total_series_processed} series, {total_new} new books, "
        f"{total_existing} skipped (already in DB)"
    )


if __name__ == "__main__":
    main()
