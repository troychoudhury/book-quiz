"""Acceptance tests for the book search API — written BEFORE implementation changes.

These tests validate the search behavior from a user's perspective:
fuzzy title matching, ISBN lookup, pagination, and empty results.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-acceptance-tests")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import case, create_engine, func as sa_func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import get_db
from app.models.base import Base
from app.models.book import Book
from app.models.question import Question, Choice

# In-memory SQLite for acceptance tests
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test and drop after."""
    # Set the get_db override per-test (not at import) so this file's engine
    # wins even when pytest imports all acceptance modules at collection time.
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_books():
    """Seed the database with a few books for search tests."""
    db = TestingSessionLocal()
    books = [
        Book(
            id=uuid.uuid4(),
            title="Harry Potter and the Sorcerer's Stone",
            author="J.K. Rowling",
            isbn="9780590353427",
            description="A young wizard discovers his magical heritage.",
        ),
        Book(
            id=uuid.uuid4(),
            title="The Hobbit",
            author="J.R.R. Tolkien",
            isbn="9780547928227",
            description="A hobbit goes on an unexpected journey.",
        ),
        Book(
            id=uuid.uuid4(),
            title="1984",
            author="George Orwell",
            isbn="9780451524935",
            description="A dystopian novel about totalitarianism.",
        ),
        Book(
            id=uuid.uuid4(),
            title="Pride and Prejudice",
            author="Jane Austen",
            isbn="9780141439518",
            description="A romantic novel about manners and marriage.",
        ),
    ]
    db.add_all(books)
    db.commit()

    # Add questions to one book so question_count can be tested
    book_with_qs = books[0]
    for ch in range(1, 4):
        q = Question(
            book_id=book_with_qs.id,
            chapter=ch,
            chapter_title=f"Chapter {ch}",
            question_text=f"Test question {ch}?",
            question_type="multiple_choice",
            difficulty="medium",
        )
        db.add(q)
        db.flush()
        for pos in range(4):
            db.add(
                Choice(
                    question_id=q.id,
                    choice_text=f"Choice {pos}",
                    is_correct=(pos == 0),
                    position=pos,
                )
            )
    db.commit()

    book_ids = [str(b.id) for b in books]
    db.close()
    return book_ids


class TestBookSearchByTitle:
    """Search books by partial title match."""

    def test_partial_title_returns_matching_books(self, client, sample_books):
        """Searching for 'Harry' returns Harry Potter."""
        response = client.get("/api/v1/books", params={"q": "Harry"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Harry Potter and the Sorcerer's Stone"
        assert data["items"][0]["author"] == "J.K. Rowling"

    def test_case_insensitive_search(self, client, sample_books):
        """Search is case-insensitive."""
        response = client.get("/api/v1/books", params={"q": "hobbit"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "The Hobbit"

    def test_search_with_no_match_returns_empty(self, client, sample_books):
        """A query matching nothing returns empty results."""
        response = client.get("/api/v1/books", params={"q": "NonexistentBookXYZ"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0


class TestBookSearchByISBN:
    """Search books by exact ISBN."""

    def test_exact_isbn_returns_correct_book(self, client, sample_books):
        """Searching by ISBN returns the exact match even if title doesn't match the query."""
        response = client.get("/api/v1/books", params={"q": "9780451524935"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "1984"

    def test_nonnumeric_isbn_returns_empty(self, client, sample_books):
        """ISBN search requires exact match; partial numeric won't match."""
        response = client.get("/api/v1/books", params={"q": "0000000000000"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


class TestBookSearchPagination:
    """Pagination returns correct pages."""

    def test_pagination_returns_correct_page(self, client, sample_books):
        """Page 1 with size 2 returns the first 2 books by title order."""
        response = client.get("/api/v1/books", params={"page": 1, "size": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["size"] == 2
        assert len(data["items"]) == 2
        # Ordered by title — "1984" comes first
        assert data["items"][0]["title"] == "1984"

    def test_page_two_returns_different_results(self, client, sample_books):
        """Page 2 returns different books than page 1."""
        page1 = client.get("/api/v1/books", params={"page": 1, "size": 2})
        page2 = client.get("/api/v1/books", params={"page": 2, "size": 2})
        assert page1.status_code == 200
        assert page2.status_code == 200
        p1_ids = {item["id"] for item in page1.json()["items"]}
        p2_ids = {item["id"] for item in page2.json()["items"]}
        assert p1_ids != p2_ids
        assert len(p1_ids & p2_ids) == 0  # No overlap


class TestBookSearchEmptyQuery:
    """Empty query returns all books."""

    def test_empty_query_returns_all_books(self, client, sample_books):
        """No query parameter returns all books."""
        response = client.get("/api/v1/books")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4

    def test_whitespace_only_query_returns_all(self, client, sample_books):
        """Whitespace-only query is treated as empty."""
        response = client.get("/api/v1/books", params={"q": "   "})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4


class TestBookSearchQuestionCount:
    """Question count is included in search results."""

    def test_book_with_questions_shows_count(self, client, sample_books):
        """Book with 3 questions shows question_count=3."""
        response = client.get("/api/v1/books", params={"q": "Harry Potter"})
        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["question_count"] == 3

    def test_book_without_questions_shows_zero(self, client, sample_books):
        """Book without questions shows question_count=0."""
        response = client.get("/api/v1/books", params={"q": "1984"})
        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["question_count"] == 0


class TestBookDetail:
    """Book detail endpoint."""

    def test_valid_book_id_returns_full_detail(self, client, sample_books):
        """GET /books/{id} returns full book info with chapters."""
        response = client.get(f"/api/v1/books/{sample_books[0]}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Harry Potter and the Sorcerer's Stone"
        assert data["chapters"] == 3
        assert data["total_questions"] == 3

    def test_invalid_uuid_returns_400(self, client):
        """Invalid UUID format returns 400."""
        response = client.get("/api/v1/books/not-a-uuid")
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_nonexistent_book_returns_404(self, client):
        """Valid UUID for nonexistent book returns 404."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/books/{fake_id}")
        assert response.status_code == 404


class _SqliteFunc:
    """Stand-in for sqlalchemy.func in the books module while tests run on SQLite.

    pg_trgm's similarity()/greatest() are PostgreSQL-only, so the acceptance
    tests patch ``app.api.books.func`` with dialect-portable SQL expressions:

      similarity(col, q) -> 1.0 exact match (case-insensitive), 0.7 substring, else 0.0
      greatest(a, b)     -> SQLite scalar max(a, b)

    This keeps the production endpoint code using the real pg_trgm functions
    while still exercising the full query/response path on SQLite.
    """

    def similarity(self, column, query):
        lowered = str(query).strip().lower()
        return case(
            (sa_func.lower(column) == lowered, 1.0),
            (sa_func.lower(column).like(f"%{lowered}%"), 0.7),
            else_=0.0,
        )

    def greatest(self, first, second):
        return sa_func.max(first, second)


@pytest.fixture
def autocomplete_funcs(monkeypatch):
    """Patch the books module's `func` so autocomplete works without pg_trgm."""
    monkeypatch.setattr("app.api.books.func", _SqliteFunc())


class TestBookAutocomplete:
    """Autocomplete suggestions — pg_trgm emulated via _SqliteFunc for SQLite."""

    def test_autocomplete_basic_title_match(
        self, client, sample_books, autocomplete_funcs
    ):
        """Typing a title fragment returns the matching book with title, author, cover."""
        response = client.get("/api/v1/books/autocomplete", params={"q": "Harry"})
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["title"] == "Harry Potter and the Sorcerer's Stone"
        assert suggestions[0]["author"] == "J.K. Rowling"
        assert "cover_url" in suggestions[0]

    def test_autocomplete_matches_author(
        self, client, sample_books, autocomplete_funcs
    ):
        """Author name fragments produce suggestions (US-2 / blocker B1)."""
        response = client.get("/api/v1/books/autocomplete", params={"q": "Rowling"})
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["author"] == "J.K. Rowling"

    def test_autocomplete_ranks_title_exact_above_author_match(
        self, client, autocomplete_funcs
    ):
        """GREATEST(similarity(title), similarity(author)) ranks title-exact above author-only."""
        db = TestingSessionLocal()
        db.add_all(
            [
                Book(
                    id=uuid.uuid4(),
                    title="Harry Potter and the Sorcerer's Stone",
                    author="J.K. Rowling",
                ),
                Book(
                    id=uuid.uuid4(),
                    title="Rowling",
                    author="Someone Else",
                    cover_url="https://example.com/rowling.jpg",
                ),
            ]
        )
        db.commit()
        db.close()

        response = client.get("/api/v1/books/autocomplete", params={"q": "Rowling"})
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert len(suggestions) == 2
        # Title-exact (1.0) beats author-substring (0.7).
        assert suggestions[0]["title"] == "Rowling"
        assert suggestions[1]["title"].startswith("Harry")
        assert suggestions[0]["cover_url"] == "https://example.com/rowling.jpg"

    def test_autocomplete_respects_limit_50(self, client, autocomplete_funcs):
        """At most 50 suggestions are returned even when more books match."""
        db = TestingSessionLocal()
        db.add_all(
            [
                Book(id=uuid.uuid4(), title=f"Common Title {i}", author="Shared Author")
                for i in range(60)
            ]
        )
        db.commit()
        db.close()

        response = client.get("/api/v1/books/autocomplete", params={"q": "common"})
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert len(suggestions) == 50
        # Secondary ordering is deterministic: title ASC.
        titles = [s["title"] for s in suggestions]
        assert titles == sorted(titles)

    def test_autocomplete_short_query_returns_empty(
        self, client, sample_books, autocomplete_funcs
    ):
        """Queries shorter than 2 characters return an empty suggestion list."""
        response = client.get("/api/v1/books/autocomplete", params={"q": "h"})
        assert response.status_code == 200
        assert response.json()["suggestions"] == []

    def test_autocomplete_trims_whitespace(
        self, client, sample_books, autocomplete_funcs
    ):
        """Surrounding whitespace is ignored."""
        response = client.get("/api/v1/books/autocomplete", params={"q": "  harry  "})
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["title"].startswith("Harry")

    def test_autocomplete_no_match_returns_empty(
        self, client, sample_books, autocomplete_funcs
    ):
        """A query matching nothing returns an empty suggestion list."""
        response = client.get("/api/v1/books/autocomplete", params={"q": "zzzxxx"})
        assert response.status_code == 200
        assert response.json()["suggestions"] == []

    def test_autocomplete_requires_no_auth(
        self, client, sample_books, autocomplete_funcs
    ):
        """Autocomplete is public — no auth token required."""
        response = client.get("/api/v1/books/autocomplete", params={"q": "Hobbit"})
        assert response.status_code == 200
        assert response.json()["suggestions"]
