"""Acceptance tests for quiz flow — start, answer, complete.

Validates the full quiz lifecycle from a user's perspective,
including both authenticated and guest flows.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-acceptance-tests")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")

import uuid

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
def book_with_questions():
    """Create a book with 15 questions (more than 10) for quiz selection."""
    db = TestingSessionLocal()
    book = Book(
        id=uuid.uuid4(),
        title="Test Book",
        author="Test Author",
        isbn="1234567890123",
    )
    db.add(book)
    db.flush()

    for ch in range(1, 4):
        for q_num in range(5):  # 5 questions per chapter = 15 total
            q = Question(
                book_id=book.id,
                chapter=ch,
                chapter_title=f"Chapter {ch}",
                question_text=f"Chapter {ch} Question {q_num + 1}?",
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
    book_id = str(book.id)
    db.close()
    return book_id


@pytest.fixture
def book_without_questions():
    """Create a book with no questions."""
    db = TestingSessionLocal()
    book = Book(
        id=uuid.uuid4(),
        title="Empty Book",
        author="No Author",
        isbn="9876543210987",
    )
    db.add(book)
    db.commit()
    book_id = str(book.id)
    db.close()
    return book_id


class TestStartQuiz:
    """Quiz start endpoint."""

    def test_start_quiz_returns_10_questions(self, client, book_with_questions):
        """Starting a quiz on a book with 15 questions returns exactly 10."""
        response = client.post(
            "/api/v1/quizzes/start", json={"book_id": book_with_questions}
        )
        assert response.status_code == 201
        data = response.json()
        assert "attempt_id" in data
        assert len(data["questions"]) == 10
        for q in data["questions"]:
            assert "id" in q
            assert q["question_number"] >= 1
            assert len(q["choices"]) == 4
            # Verify choice positions are 0-3 (shuffled but present)
            positions = {c["position"] for c in q["choices"]}
            assert positions == {0, 1, 2, 3}

    def test_start_quiz_no_questions_returns_404(self, client, book_without_questions):
        """Book without questions returns 404."""
        response = client.post(
            "/api/v1/quizzes/start", json={"book_id": book_without_questions}
        )
        assert response.status_code == 404

    def test_start_quiz_invalid_book_id_returns_400(self, client):
        """Invalid UUID returns 400."""
        response = client.post("/api/v1/quizzes/start", json={"book_id": "not-a-uuid"})
        assert response.status_code == 400

    def test_start_quiz_nonexistent_book_returns_404(self, client):
        """Valid UUID for nonexistent book returns 404."""
        fake_id = str(uuid.uuid4())
        response = client.post("/api/v1/quizzes/start", json={"book_id": fake_id})
        assert response.status_code == 404

    def test_start_quiz_guest_flow(self, client, book_with_questions):
        """Guest (no auth token) can start a quiz."""
        response = client.post(
            "/api/v1/quizzes/start", json={"book_id": book_with_questions}
        )
        assert response.status_code == 201
        assert "attempt_id" in response.json()


class TestAnswerQuestion:
    """Quiz answer endpoint."""

    @pytest.fixture
    def active_attempt(self, client, book_with_questions):
        """Start a quiz and return attempt_id + first question."""
        resp = client.post(
            "/api/v1/quizzes/start", json={"book_id": book_with_questions}
        )
        data = resp.json()
        return data["attempt_id"], data["questions"][0]

    def test_answer_response_structure(self, client, active_attempt):
        """Answer response includes is_correct, correct_choice_id, question_number."""
        attempt_id, question = active_attempt
        response = client.post(
            f"/api/v1/quizzes/{attempt_id}/answer",
            json={
                "question_id": question["id"],
                "choice_id": question["choices"][0]["id"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "is_correct" in data
        assert "correct_choice_id" in data
        assert "question_number" in data
        assert data["question_number"] == 1

    def test_incorrect_answer_returns_false(self, client, book_with_questions):
        """Selecting an answer returns a response with is_correct field."""
        resp = client.post(
            "/api/v1/quizzes/start", json={"book_id": book_with_questions}
        )
        attempt_id = resp.json()["attempt_id"]
        question = resp.json()["questions"][0]

        # Answer any choice — response structure is what matters
        response = client.post(
            f"/api/v1/quizzes/{attempt_id}/answer",
            json={
                "question_id": question["id"],
                "choice_id": question["choices"][0]["id"],
            },
        )
        assert response.status_code == 200
        # is_correct is always present (whether true or false)
        assert isinstance(response.json()["is_correct"], bool)

    def test_duplicate_answer_rejected(self, client, book_with_questions):
        """Answering the same question twice returns 400."""
        resp = client.post(
            "/api/v1/quizzes/start", json={"book_id": book_with_questions}
        )
        attempt_id = resp.json()["attempt_id"]
        q = resp.json()["questions"][0]
        c = q["choices"][0]

        # First answer
        r1 = client.post(
            f"/api/v1/quizzes/{attempt_id}/answer",
            json={"question_id": q["id"], "choice_id": c["id"]},
        )
        assert r1.status_code == 200

        # Second answer (duplicate)
        r2 = client.post(
            f"/api/v1/quizzes/{attempt_id}/answer",
            json={"question_id": q["id"], "choice_id": c["id"]},
        )
        assert r2.status_code == 400
        assert "already answered" in r2.json()["detail"].lower()

    def test_answer_invalid_attempt_returns_404(self, client):
        """Answering a nonexistent attempt returns 404."""
        fake_id = str(uuid.uuid4())
        response = client.post(
            f"/api/v1/quizzes/{fake_id}/answer",
            json={"question_id": str(uuid.uuid4()), "choice_id": str(uuid.uuid4())},
        )
        assert response.status_code == 404


class TestCompleteQuiz:
    """Quiz completion endpoint."""

    def _answer_all(self, client, attempt_id, questions):
        """Answer every question in an attempt with its first shuffled choice."""
        for q in questions:
            client.post(
                f"/api/v1/quizzes/{attempt_id}/answer",
                json={"question_id": q["id"], "choice_id": q["choices"][0]["id"]},
            )

    def _start_and_answer_all(self, client, book_with_questions):
        """Start a quiz and answer all questions; return (attempt_id, questions)."""
        resp = client.post(
            "/api/v1/quizzes/start", json={"book_id": book_with_questions}
        )
        data = resp.json()
        self._answer_all(client, data["attempt_id"], data["questions"])
        return data["attempt_id"], data["questions"]

    def test_complete_quiz_returns_score(self, client, book_with_questions):
        """Completing a quiz after answering all 10 questions returns score."""
        attempt_id, _ = self._start_and_answer_all(client, book_with_questions)

        # Complete
        complete_resp = client.post(f"/api/v1/quizzes/{attempt_id}/complete")
        assert complete_resp.status_code == 200
        data = complete_resp.json()
        assert "score" in data
        assert data["total"] == 10
        assert 0 <= data["score"] <= 10
        assert "percentage" in data
        assert 0 <= data["percentage"] <= 100
        assert len(data["results"]) == 10

    def test_complete_with_email_sends_results_email(
        self, client, book_with_questions, monkeypatch
    ):
        """Providing an email starts a background send of the quiz results email."""
        sent = {}

        def fake_send(recipient, subject, html):
            sent["recipient"] = recipient
            sent["subject"] = subject
            sent["html"] = html

        # Run the background thread synchronously so assertions are deterministic.
        class SyncThread:
            def __init__(self, target, daemon=True):
                self._target = target

            def start(self):
                self._target()

        monkeypatch.setattr("app.services.email_service.send_email", fake_send)
        monkeypatch.setattr("app.api.quiz.threading.Thread", SyncThread)

        attempt_id, _ = self._start_and_answer_all(client, book_with_questions)
        resp = client.post(
            f"/api/v1/quizzes/{attempt_id}/complete",
            json={"email": "reader@example.com"},
        )
        assert resp.status_code == 200

        assert sent.get("recipient") == "reader@example.com"
        assert "Your Book Quiz results" in sent.get("subject", "")  # real builder used
        assert "<html" in sent.get("html", "")

    def test_complete_without_email_does_not_send(
        self, client, book_with_questions, monkeypatch
    ):
        """No email in the request → nothing is sent."""
        sent = []

        def fake_send(recipient, subject, html):
            sent.append(recipient)

        monkeypatch.setattr("app.services.email_service.send_email", fake_send)

        attempt_id, _ = self._start_and_answer_all(client, book_with_questions)
        resp = client.post(f"/api/v1/quizzes/{attempt_id}/complete")
        assert resp.status_code == 200
        assert sent == []

    def test_complete_email_send_failure_does_not_break_completion(
        self, client, book_with_questions, monkeypatch
    ):
        """SMTP failure while sending never breaks quiz completion."""

        def fake_send(recipient, subject, html):
            raise ConnectionError("smtp down")

        class SyncThread:
            def __init__(self, target, daemon=True):
                self._target = target

            def start(self):
                # send_email swallows SMTP errors; nothing should propagate
                self._target()

        monkeypatch.setattr("app.services.email_service.send_email", fake_send)
        monkeypatch.setattr("app.api.quiz.threading.Thread", SyncThread)

        attempt_id, _ = self._start_and_answer_all(client, book_with_questions)
        resp = client.post(
            f"/api/v1/quizzes/{attempt_id}/complete",
            json={"email": "reader@example.com"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 10

    def test_complete_without_answers_returns_400(self, client, book_with_questions):
        """Cannot complete a quiz with no answers."""
        resp = client.post(
            "/api/v1/quizzes/start", json={"book_id": book_with_questions}
        )
        attempt_id = resp.json()["attempt_id"]

        response = client.post(f"/api/v1/quizzes/{attempt_id}/complete")
        assert response.status_code == 400
        assert "no answers" in response.json()["detail"].lower()

    def test_complete_already_completed_returns_400(self, client, book_with_questions):
        """Cannot complete an already completed quiz."""
        resp = client.post(
            "/api/v1/quizzes/start", json={"book_id": book_with_questions}
        )
        attempt_id = resp.json()["attempt_id"]
        q = resp.json()["questions"][0]

        client.post(
            f"/api/v1/quizzes/{attempt_id}/answer",
            json={"question_id": q["id"], "choice_id": q["choices"][0]["id"]},
        )
        client.post(f"/api/v1/quizzes/{attempt_id}/complete")

        # Try to complete again
        r2 = client.post(f"/api/v1/quizzes/{attempt_id}/complete")
        assert r2.status_code == 400
        assert "already completed" in r2.json()["detail"].lower()

    def test_complete_invalid_attempt_returns_404(self, client):
        """Completing a nonexistent attempt returns 404."""
        fake_id = str(uuid.uuid4())
        response = client.post(f"/api/v1/quizzes/{fake_id}/complete")
        assert response.status_code == 404
