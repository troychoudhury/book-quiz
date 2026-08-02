"""User profile API endpoints (authenticated)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.book import Book
from app.models.quiz import QuizAttempt
from app.models.user import User

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class AttemptSummary(BaseModel):
    attempt_number: int
    score: int | None
    total: int
    completed_at: str | None

    model_config = {"from_attributes": True}


class BookProgress(BaseModel):
    book_id: str
    title: str
    author: str
    attempts: list[AttemptSummary]
    best_score: int = 0
    total_questions_answered: int = 0


class ProfileResponse(BaseModel):
    id: str
    email: str
    display_name: str
    total_quizzes: int
    total_questions_answered: int
    books: list[BookProgress]


@router.get("/me/profile", response_model=ProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the authenticated user's profile with book progress."""
    attempts = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.user_id == current_user.id, QuizAttempt.completed_at.isnot(None))
        .order_by(QuizAttempt.completed_at)
        .all()
    )

    # Group completed attempts by book
    book_map: dict[uuid.UUID, list[QuizAttempt]] = {}
    for attempt in attempts:
        book_map.setdefault(attempt.book_id, []).append(attempt)

    books: list[BookProgress] = []
    total_answered = 0
    for book_id, book_attempts in book_map.items():
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            continue
        attempts_summary = [
            AttemptSummary(
                attempt_number=a.attempt_number,
                score=a.score,
                total=a.total_questions,
                completed_at=a.completed_at.isoformat() if a.completed_at else None,
            )
            for a in book_attempts
        ]
        answered = sum(a.total_questions for a in book_attempts if a.total_questions)
        total_answered += answered
        best = max((a.score or 0) for a in book_attempts if a.score is not None) if any(
            a.score is not None for a in book_attempts
        ) else 0
        books.append(
            BookProgress(
                book_id=str(book.id),
                title=book.title,
                author=book.author,
                attempts=attempts_summary,
                best_score=best,
                total_questions_answered=answered,
            )
        )

    return ProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        display_name=current_user.display_name,
        total_quizzes=len(attempts),
        total_questions_answered=total_answered,
        books=books,
    )


@router.get("/me/books/{book_id}/progress")
def get_book_progress(
    book_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed progress for a specific book."""
    try:
        bid = uuid.UUID(book_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid book ID.")

    book = db.query(Book).filter(Book.id == bid).first()
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found.")

    attempts = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.book_id == bid,
            QuizAttempt.completed_at.isnot(None),
        )
        .order_by(QuizAttempt.attempt_number)
        .all()
    )

    return {
        "book_id": str(book.id),
        "title": book.title,
        "author": book.author,
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "score": a.score,
                "total": a.total_questions,
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            }
            for a in attempts
        ],
        "total_questions_answered": sum(a.total_questions for a in attempts),
    }
