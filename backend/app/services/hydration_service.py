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

# Per-age subject lists, ordered primary → secondary. All subjects verified to
# return results against OpenLibrary's search API. Multiple subjects per age give
# each grade level diverse books instead of sharing one coarse subject.
# Age 18 (adult) reuses verified subjects to preserve the previous mapping.
OPENLIBRARY_SUBJECTS: dict[int, list[str]] = {
    6: ["easy_readers", "picture_books", "children's_stories"],
    7: ["readers_elementary", "juvenile_fiction", "animals_juvenile_fiction"],
    8: ["chapter_books", "school_stories", "humorous_stories"],
    9: ["juvenile_fiction", "adventure_stories", "detective_and_mystery_stories"],
    10: [
        "middle_school_fiction",
        "fantasy_juvenile_fiction",
        "friendship_juvenile_fiction",
    ],
    11: [
        "children's_stories",
        "science_fiction_juvenile",
        "historical_fiction_juvenile",
    ],
    12: ["juvenile_fiction", "action_and_adventure", "fantasy"],
    13: ["young_adult_fiction", "coming_of_age", "school_stories"],
    14: ["young_adult_fiction", "romance_fiction", "mystery_fiction"],
    15: ["science_fiction", "fantasy_fiction", "young_adult_fiction"],
    16: ["historical_fiction", "dystopian_fiction", "young_adult_fiction"],
    17: ["fantasy", "science_fiction", "young_adult_fiction"],
    18: ["fantasy", "science_fiction", "young_adult_fiction"],
}

# School grade (1-12) → lower age bound used for OpenLibrary queries.
# _store_book sets age_range_lower=age and age_range_upper=age+2, which
# reasonably encompasses each grade's age range.
GRADE_AGE_MAP: dict[int, int] = {
    1: 6,
    2: 7,
    3: 8,
    4: 9,
    5: 10,
    6: 11,
    7: 12,
    8: 13,
    9: 14,
    10: 15,
    11: 16,
    12: 17,
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
        subjects = self._subjects_for_age(age)
        logger.info(
            f"Fetching up to {limit} books for age {age} (subjects: {subjects})"
        )

        stored: list[dict] = []
        existing_isbns = self._get_existing_isbns()

        try:
            with httpx.Client(timeout=30.0) as client:
                # Pagination resets per subject so each subject contributes
                # its top results (page 1) before we page deeper. If one
                # subject is exhausted, the next subject is tried.
                for subject in subjects:
                    if len(stored) >= limit:
                        break
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
                            # Subject exhausted — move on to the next subject.
                            break
                        page += 1

        except Exception as e:
            logger.error(f"Failed to fetch books: {e}")
            raise

        logger.info(f"Stored {len(stored)} new books for age {age}")
        return stored

    def _subjects_for_age(self, age: int) -> list[str]:
        """Return the ordered subject list to query for an age.

        Appends the broad age-appropriate subject as a final fallback so a
        grade that falls short of the limit still gets a top-up attempt.
        """
        subjects = list(OPENLIBRARY_SUBJECTS.get(age, ["juvenile_fiction"]))
        fallback = "juvenile_fiction" if age <= 12 else "young_adult_fiction"
        if fallback not in subjects:
            subjects.append(fallback)
        return subjects

    def _get_existing_isbns(self) -> set[str]:
        """Return set of ISBNs already in the database.

        Note: a full-table ISBN scan is acceptable at the current scale
        (<10K books, per ADR-002). If the catalog grows significantly,
        replace this with an ``INSERT ... ON CONFLICT (isbn) DO NOTHING``
        upsert so dedup happens in the database instead of in memory.
        """
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
        """Generate AI-powered quiz questions for a book and store them.

        Uses the QuestionGenerator to produce 10 questions via OpenAI,
        then stores them + choices in the database. Works without
        explicit chapter data — the AI uses its knowledge of the book.

        Args:
            book_id: UUID of the book

        Returns:
            Number of questions stored (0 if no OpenAI key or on error)
        """
        from app.core.config import get_settings
        from app.models.question import Question, Choice
        from app.services.question_generator import QuestionGenerator

        settings = get_settings()

        book = self.db.query(Book).filter(Book.id == book_id).first()
        if not book:
            logger.error(f"Book {book_id} not found")
            return 0

        # Skip if already has questions
        existing = self.db.query(Question).filter(Question.book_id == book_id).count()
        if existing > 0:
            logger.info(f"Book {book_id} already has {existing} questions — skipping")
            return existing

        age_range = ""
        if book.age_range_lower and book.age_range_upper:
            age_range = f"{book.age_range_lower}-{book.age_range_upper}"

        generator = QuestionGenerator(
            api_key=settings.openai_api_key or self.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )
        generated = generator.generate_for_book_with_chapters(
            book_title=book.title,
            author=book.author,
            age_range=age_range,
        )

        if not generated:
            return 0

        stored = 0
        for gq in generated:
            question = Question(
                id=uuid4(),
                book_id=book_id,
                chapter=gq.chapter,
                chapter_title=gq.chapter_title or None,
                question_text=gq.question_text,
                question_type=gq.question_type,
                difficulty=gq.difficulty,
            )
            self.db.add(question)
            self.db.flush()

            for i, gc in enumerate(gq.choices):
                choice = Choice(
                    id=uuid4(),
                    question_id=question.id,
                    choice_text=gc.text,
                    is_correct=gc.is_correct,
                    position=i,
                )
                self.db.add(choice)
            stored += 1

        self.db.commit()
        logger.info(f"Stored {stored} questions for book {book_id} ('{book.title}')")
        return stored
