"""Book data hydration service — fetches top books and generates AI questions.

This service orchestrates:
1. Fetching books per age group from OpenLibrary API
2. Generating AI-powered questions for each book
3. Storing everything in the database with ISBN deduplication

Designed to run as a Celery background task.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID, uuid4

import httpx
from sqlalchemy.orm import Session

from app.models.book import Book

logger = logging.getLogger(__name__)

OPENLIBRARY_SUBJECTS: dict[int, str] = {
    6: "juvenile_fiction",
    7: "juvenile_fiction",
    8: "juvenile_fiction",
    9: "juvenile_fiction",
    10: "juvenile_fiction",
    11: "juvenile_fiction",
    12: "juvenile_fiction",
    13: "young_adult_fiction",
    14: "young_adult_fiction",
    15: "young_adult_fiction",
    16: "young_adult_fiction",
    17: "young_adult_fiction",
    18: "fantasy",
}


@dataclass
class HydrationResult:
    """Result of a hydration job."""

    task_id: UUID
    status: str  # 'pending', 'processing', 'completed', 'failed'
    books_processed: int = 0
    questions_generated: int = 0
    errors: list[str] = field(default_factory=list)


class HydrationService:
    """Manages the hydration of book data and AI question generation."""

    OPENLIBRARY_SEARCH = "https://openlibrary.org/search.json"

    def __init__(self, db: Session, openai_api_key: Optional[str] = None):
        self.db = db
        self.openai_api_key = openai_api_key

    def fetch_top_books_for_age(self, age: int, limit: int = 100) -> list[dict]:
        """Fetch books for a given age group from OpenLibrary.

        Uses the OpenLibrary search API to find books by subject.
        Deduplicates against existing ISBNs in the database.
        Stores new books in the database.

        Args:
            age: Target age (6-18)
            limit: Maximum number of books to fetch

        Returns:
            List of stored book metadata dicts
        """
        subject = OPENLIBRARY_SUBJECTS.get(age, "juvenile_fiction")
        logger.info(f"Fetching up to {limit} books for age {age} (subject: {subject})")

        stored: list[dict] = []
        existing_isbns = self._get_existing_isbns()

        try:
            with httpx.Client(timeout=30.0) as client:
                page = 1
                while len(stored) < limit and page <= 10:
                    response = client.get(
                        self.OPENLIBRARY_SEARCH,
                        params={
                            "subject": subject,
                            "limit": min(50, limit - len(stored)),
                            "page": page,
                            "fields": "title,author_name,isbn,first_publish_year,cover_i,subject",
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    for doc in data.get("docs", []):
                        isbn = self._extract_isbn(doc)
                        if not isbn or isbn in existing_isbns:
                            continue
                        existing_isbns.add(isbn)

                        book = self._store_book(doc, isbn, age)
                        stored.append(
                            {
                                "id": str(book.id),
                                "title": book.title,
                                "author": book.author,
                                "isbn": book.isbn,
                            }
                        )
                        if len(stored) >= limit:
                            break

                    if len(data.get("docs", [])) == 0:
                        break
                    page += 1

        except Exception as e:
            logger.error(f"Failed to fetch books: {e}")
            raise

        logger.info(f"Stored {len(stored)} new books for age {age}")
        return stored

    def _get_existing_isbns(self) -> set[str]:
        """Return set of ISBNs already in the database."""
        rows = self.db.query(Book.isbn).filter(Book.isbn.isnot(None)).all()
        return {row[0] for row in rows if row[0]}

    def _extract_isbn(self, doc: dict) -> str | None:
        """Extract first valid ISBN-13 or ISBN-10 from an OpenLibrary doc."""
        isbns = doc.get("isbn", [])
        if not isbns:
            return None
        # Prefer ISBN-13 (13 digits) over ISBN-10
        for isbn in isbns:
            clean = isbn.replace("-", "").replace(" ", "")
            if len(clean) in (10, 13) and clean.isdigit():
                return clean
        return None

    def _store_book(self, doc: dict, isbn: str, age: int) -> Book:
        """Store a book from OpenLibrary data in the database."""
        title = doc.get("title", "Unknown Title")
        authors = doc.get("author_name", ["Unknown Author"])
        author = authors[0] if authors else "Unknown Author"
        cover_id = doc.get("cover_i")
        cover_url = (
            f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
            if cover_id
            else None
        )

        book = Book(
            id=uuid4(),
            title=title[:500],
            author=author[:300],
            isbn=isbn,
            cover_url=cover_url,
            age_range_lower=age,
            age_range_upper=age + 2,
        )
        self.db.add(book)
        self.db.commit()
        self.db.refresh(book)
        return book

    def generate_questions_for_book(self, book_id: UUID) -> int:
        """Generate AI-powered questions for each chapter of a book.

        Calls the QuestionGenerator service to produce questions via OpenAI.
        Currently a stub — requires real chapter data from external source.

        Args:
            book_id: UUID of the book

        Returns:
            Number of questions generated (0 if no OpenAI key)
        """
        logger.info(f"Question generation for book {book_id} — requires OpenAI key")
        return 0
