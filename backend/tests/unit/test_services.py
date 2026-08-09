"""Unit tests for hydration service and question generator."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-acceptance-tests")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.book import Book
from app.services.hydration_service import HydrationService
from app.services.question_generator import QuestionGenerator


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


class TestHydrationService:
    """Tests for the hydration service."""

    def test_get_existing_isbns_empty(self, db_session):
        """Empty database returns empty ISBN set."""
        service = HydrationService(db_session)
        isbns = service._get_existing_isbns()
        assert isbns == set()

    def test_get_existing_isbns_with_books(self, db_session):
        """Returns existing ISBNs from database."""
        book = Book(
            id=uuid.uuid4(),
            title="Test",
            author="Author",
            isbn="1234567890",
        )
        db_session.add(book)
        db_session.commit()

        service = HydrationService(db_session)
        isbns = service._get_existing_isbns()
        assert "1234567890" in isbns

    def test_extract_isbn_returns_valid(self, db_session):
        """Extracts first valid ISBN from OpenLibrary doc."""
        service = HydrationService(db_session)
        isbn = service._extract_isbn({"isbn": ["9780141439518", "0141439513"]})
        assert isbn == "9780141439518"

    def test_extract_isbn_no_isbns(self, db_session):
        """Returns None when no ISBNs present."""
        service = HydrationService(db_session)
        isbn = service._extract_isbn({"title": "No ISBN"})
        assert isbn is None

    def test_extract_isbn_invalid_format(self, db_session):
        """Filters out invalid ISBN formats."""
        service = HydrationService(db_session)
        isbn = service._extract_isbn({"isbn": ["not-an-isbn", "1234567890"]})
        assert isbn == "1234567890"

    def test_store_book_creates_record(self, db_session):
        """Store book creates a database record."""
        service = HydrationService(db_session)
        doc = {
            "title": "Test Book",
            "author_name": ["Test Author"],
            "cover_i": 12345,
        }
        book = service._store_book(doc, "1234567890", 10)
        assert book.title == "Test Book"
        assert book.author == "Test Author"
        assert book.isbn == "1234567890"
        assert book.cover_url == "https://covers.openlibrary.org/b/id/12345-M.jpg"

        # Verify persisted
        found = db_session.query(Book).filter(Book.isbn == "1234567890").first()
        assert found is not None

    @patch("httpx.Client.get")
    def test_fetch_top_books_for_age_integration(self, mock_get, db_session):
        """Fetch books parses OpenLibrary response and stores books."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "docs": [
                {
                    "title": "Harry Potter",
                    "author_name": ["J.K. Rowling"],
                    "isbn": ["9780590353427"],
                    "cover_i": 789,
                },
                {
                    "title": "The Hobbit",
                    "author_name": ["J.R.R. Tolkien"],
                    "isbn": ["9780547928227"],
                },
            ]
        }
        mock_get.return_value = mock_response

        service = HydrationService(db_session)
        books = service.fetch_top_books_for_age(10, limit=10)
        assert len(books) == 2
        assert books[0]["title"] == "Harry Potter"
        assert books[1]["title"] == "The Hobbit"

    @patch("httpx.Client.get")
    def test_fetch_deduplicates_by_isbn(self, mock_get, db_session):
        """Books already in DB are skipped."""
        existing = Book(
            id=uuid.uuid4(),
            title="Existing",
            author="Author",
            isbn="9780590353427",
        )
        db_session.add(existing)
        db_session.commit()

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "docs": [
                {
                    "title": "Harry Potter",
                    "author_name": ["J.K. Rowling"],
                    "isbn": ["9780590353427"],  # Already exists
                },
                {
                    "title": "New Book",
                    "author_name": ["New Author"],
                    "isbn": ["9780000000001"],
                },
            ]
        }
        mock_get.return_value = mock_response

        service = HydrationService(db_session)
        books = service.fetch_top_books_for_age(10, limit=10)
        assert len(books) == 1
        assert books[0]["title"] == "New Book"

    # ── Multi-subject fetch logic (T1 review findings) ─────────────────────

    @staticmethod
    def _page_response(docs: list[dict]) -> MagicMock:
        """Build a mocked httpx response with the given OpenLibrary docs."""
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"docs": docs}
        return resp

    @staticmethod
    def _doc(title: str, isbn: str) -> dict:
        return {"title": title, "author_name": ["Author"], "isbn": [isbn]}

    @patch("httpx.Client.get")
    def test_fetch_falls_through_subjects(self, mock_get, db_session):
        """Subject fallthrough: an empty subject moves on to the next one."""
        empty = self._page_response([])
        full = self._page_response([self._doc("Book A", "9780000000001")])
        mock_get.side_effect = [empty, full]

        service = HydrationService(db_session)
        books = service.fetch_top_books_for_age(10, limit=1)

        assert len(books) == 1
        assert books[0]["title"] == "Book A"
        subjects = [c.kwargs["params"]["subject"] for c in mock_get.call_args_list]
        assert len(subjects) == 2
        assert subjects[0] != subjects[1]  # second subject was tried

    @patch("httpx.Client.get")
    def test_fetch_pagination_resets_per_subject(self, mock_get, db_session):
        """Pagination reset: each subject starts paging from page 1."""
        mock_get.side_effect = [
            self._page_response([self._doc("b1", "9780000000001")]),
            self._page_response([]),  # subject 1 exhausted after 1 page
            self._page_response([self._doc("b2", "9780000000002")]),
        ]

        service = HydrationService(db_session)
        books = service.fetch_top_books_for_age(10, limit=2)

        assert [b["title"] for b in books] == ["b1", "b2"]
        pages = [c.kwargs["params"]["page"] for c in mock_get.call_args_list]
        assert pages == [1, 2, 1]  # subject 2 restarts paging from page 1

    @patch("httpx.Client.get")
    def test_fetch_spreads_remaining_limit(self, mock_get, db_session):
        """Limit spread: the last page asks for only the remaining books."""
        page1_docs = [self._doc(f"b{i}", f"978{i:010d}") for i in range(50)]
        page2_docs = [self._doc(f"b{i}", f"978{i:010d}") for i in range(50, 60)]
        mock_get.side_effect = [
            self._page_response(page1_docs),
            self._page_response(page2_docs),
        ]

        service = HydrationService(db_session)
        books = service.fetch_top_books_for_age(10, limit=60)

        assert len(books) == 60
        limits = [c.kwargs["params"]["limit"] for c in mock_get.call_args_list]
        assert limits == [50, 10]  # second page asks only for the remaining 10

    @patch("httpx.Client.get")
    def test_fetch_stops_paging_on_all_duplicate_page(self, mock_get, db_session):
        """Dedup-heavy page: a full page of known ISBNs stops deeper paging."""
        known = ["9780000000001", "9780000000002", "9780000000003"]
        for isbn in known:
            db_session.add(Book(id=uuid.uuid4(), title="E", author="A", isbn=isbn))
        db_session.commit()

        dup_page = self._page_response([self._doc("dup", isbn) for isbn in known] * 17)
        mock_get.return_value = dup_page  # every page is all-duplicates

        service = HydrationService(db_session)
        books = service.fetch_top_books_for_age(10, limit=100)

        assert books == []
        calls = mock_get.call_args_list
        # One page per subject (no deeper paging) — pages never advance past 1.
        assert len(calls) == len(service._subjects_for_age(10))
        assert all(c.kwargs["params"]["page"] == 1 for c in calls)

    @patch("httpx.Client.get")
    def test_fetch_rolls_back_all_books_on_failure(self, mock_get, db_session):
        """Per-grade atomicity: a mid-fetch failure rolls back every book."""
        import httpx

        ok = self._page_response([self._doc("A", "9780000000001")])
        boom = MagicMock()
        boom.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_get.side_effect = [ok, boom]

        service = HydrationService(db_session)
        with pytest.raises(httpx.HTTPStatusError):
            service.fetch_top_books_for_age(10, limit=100, commit=True)

        # The book flushed before the failure must not be persisted.
        assert db_session.query(Book).count() == 0


class TestQuestionGenerator:
    """Tests for the AI question generator."""

    def test_no_api_key_returns_empty(self):
        """Without API key, generator returns empty list."""
        gen = QuestionGenerator(api_key=None)
        result = gen.generate_for_chapter(
            "Test Book", "Author", 1, "Chapter 1", "A summary."
        )
        assert result == []

    def test_client_is_none_without_key(self):
        """Client property returns None without API key."""
        gen = QuestionGenerator(api_key=None)
        assert gen.client is None

    def test_client_created_with_key(self):
        """Client is created when API key is provided."""
        gen = QuestionGenerator(api_key="sk-test-key")
        assert gen.client is not None

    def test_build_prompt_includes_book_info(self):
        """Prompt contains all required book/chapter information."""
        gen = QuestionGenerator(api_key="sk-test")
        prompt = gen._build_prompt(
            "Test Book", "Author Name", 3, "Chapter Three", "Summary text"
        )
        assert "Test Book" in prompt
        assert "Author Name" in prompt
        assert "Chapter 3" in prompt
        assert "Chapter Three" in prompt
        assert "Summary text" in prompt
        assert "10 multiple-choice" in prompt
        assert "all of the above" in prompt.lower()

    @patch("openai.OpenAI")
    def test_generate_parses_valid_response(self, mock_openai_class):
        """Valid JSON response is parsed into GeneratedQuestion objects."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"questions": [{"question_text": "What is the theme?", "question_type": "theme", "difficulty": "medium", "choices": [{"text": "Love", "is_correct": true}, {"text": "Hate", "is_correct": false}, {"text": "Fear", "is_correct": false}, {"text": "Joy", "is_correct": false}]}]}'
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_completion

        gen = QuestionGenerator(api_key="sk-test")
        gen._client = mock_client  # Bypass lazy init

        result = gen.generate_for_chapter("Book", "Author", 1, "Ch1", "Summary")
        assert len(result) == 1
        assert result[0].question_text == "What is the theme?"
        assert result[0].question_type == "theme"
        assert len(result[0].choices) == 4

    @patch("openai.OpenAI")
    def test_generate_handles_api_error(self, mock_openai_class):
        """API errors return empty list."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        gen = QuestionGenerator(api_key="sk-test")
        gen._client = mock_client

        result = gen.generate_for_chapter("Book", "Author", 1, "Ch1", "Summary")
        assert result == []
