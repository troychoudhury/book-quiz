"""Acceptance tests for user profile API — profile and book progress."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-acceptance-tests")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import get_db
from app.models.base import Base
from app.models.book import Book
from app.models.question import Question, Choice
from app.models.quiz import QuizAttempt, QuizAnswer
from app.services.auth_service import AuthService

# In-memory SQLite
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
def auth_headers():
    """Create a user and return auth headers + user info."""
    db = TestingSessionLocal()
    auth = AuthService(db)

    user = auth.register(
        email="profile_test@example.com",
        password="SecurePass123!",
        display_name="Profile Tester",
    )

    access_token = auth.create_access_token(user.id)
    db.close()
    return {"Authorization": f"Bearer {access_token}"}, str(user.id)


@pytest.fixture
def book_with_progress(auth_headers):
    """Create a book with questions and completed quiz attempts for the test user."""
    db = TestingSessionLocal()
    _, user_id = auth_headers
    uid = uuid.UUID(user_id)

    book = Book(
        id=uuid.uuid4(),
        title="Progress Test Book",
        author="Test Author",
        isbn="1111111111111",
        cover_url="https://example.com/cover.jpg",
    )
    db.add(book)
    db.flush()

    # Add 15 questions
    for ch in range(1, 4):
        for q_num in range(5):
            q = Question(
                book_id=book.id,
                chapter=ch,
                chapter_title=f"Chapter {ch}",
                question_text=f"Ch{ch} Q{q_num+1}?",
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

    # Create 2 completed attempts
    for attempt_num in range(1, 3):
        attempt = QuizAttempt(
            user_id=uid,
            book_id=book.id,
            total_questions=10,
            attempt_number=attempt_num,
            score=7 + attempt_num,  # 8, 9
            completed_at=datetime.now(timezone.utc),
        )
        db.add(attempt)
        db.flush()
        # Add some answers
        questions = (
            db.query(Question).filter(Question.book_id == book.id).limit(10).all()
        )
        for q in questions:
            choice = db.query(Choice).filter(Choice.question_id == q.id).first()
            db.add(
                QuizAnswer(
                    attempt_id=attempt.id,
                    question_id=q.id,
                    selected_choice_id=choice.id,
                    is_correct=choice.is_correct,
                )
            )

    book_id = str(book.id)
    db.commit()
    db.close()
    return book_id


class TestProfileEndpoint:
    """GET /users/me/profile"""

    def test_unauthenticated_returns_401(self, client):
        """Profile endpoint requires authentication."""
        response = client.get("/api/v1/users/me/profile")
        assert response.status_code == 401

    def test_profile_returns_user_info(self, client, auth_headers):
        """Profile includes user id, email, display_name."""
        headers, _ = auth_headers
        response = client.get("/api/v1/users/me/profile", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "profile_test@example.com"
        assert data["display_name"] == "Profile Tester"
        assert "id" in data

    def test_profile_includes_book_progress(
        self, client, auth_headers, book_with_progress
    ):
        """Profile includes books with attempt history."""
        headers, _ = auth_headers
        response = client.get("/api/v1/users/me/profile", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["books"]) == 1
        book = data["books"][0]
        assert book["title"] == "Progress Test Book"
        assert book["cover_url"] == "https://example.com/cover.jpg"
        assert book["best_score"] == 9  # best of 8, 9
        assert book["total_questions_answered"] == 20  # 2 attempts × 10
        assert book["remaining_questions"] == 0  # 15 total - 20 answered = 0 (clamped)
        assert len(book["attempts"]) == 2

    def test_profile_no_completed_quizzes(self, client, auth_headers):
        """New user has zero quizzes and empty books."""
        headers, _ = auth_headers
        response = client.get("/api/v1/users/me/profile", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_quizzes"] == 0
        assert data["total_questions_answered"] == 0
        assert data["books"] == []


class TestBookProgressEndpoint:
    """GET /users/me/books/{book_id}/progress"""

    def test_unauthenticated_returns_401(self, client, book_with_progress):
        """Progress endpoint requires authentication."""
        response = client.get(f"/api/v1/users/me/books/{book_with_progress}/progress")
        assert response.status_code == 401

    def test_progress_returns_detailed_info(
        self, client, auth_headers, book_with_progress
    ):
        """Progress includes total_questions, remaining, can_retake."""
        headers, _ = auth_headers
        response = client.get(
            f"/api/v1/users/me/books/{book_with_progress}/progress", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Progress Test Book"
        assert data["cover_url"] == "https://example.com/cover.jpg"
        assert data["total_questions"] == 15
        assert data["total_questions_answered"] == 20
        assert data["remaining_questions"] == 0
        assert data["can_retake"] is False  # no remaining questions
        assert data["attempts_completed"] == 2

    def test_progress_invalid_book_id_returns_400(self, client, auth_headers):
        """Invalid UUID returns 400."""
        headers, _ = auth_headers
        response = client.get(
            "/api/v1/users/me/books/not-a-uuid/progress", headers=headers
        )
        assert response.status_code == 400

    def test_progress_nonexistent_book_returns_404(self, client, auth_headers):
        """Valid UUID for nonexistent book returns 404."""
        headers, _ = auth_headers
        fake_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/users/me/books/{fake_id}/progress", headers=headers
        )
        assert response.status_code == 404

    def test_progress_unattempted_book(self, client, auth_headers):
        """Book with no attempts returns zero progress."""
        headers, _ = auth_headers
        db = TestingSessionLocal()
        book = Book(
            id=uuid.uuid4(),
            title="Unattempted Book",
            author="No One",
            isbn="2222222222222",
        )
        # Add a question so can_retake is meaningful
        db.add(book)
        db.flush()
        q = Question(
            book_id=book.id,
            chapter=1,
            question_text="Test?",
            question_type="multiple_choice",
        )
        db.add(q)
        db.commit()
        book_id = str(book.id)
        db.close()

        response = client.get(
            f"/api/v1/users/me/books/{book_id}/progress", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["attempts_completed"] == 0
        assert data["total_questions_answered"] == 0
        assert data["total_questions"] == 1
        assert data["can_retake"] is True  # has questions, not attempted
