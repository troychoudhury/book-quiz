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
from app.models.user_oauth_link import UserOAuthLink

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
    cover_url: str | None = None
    attempts: list[AttemptSummary]
    best_score: int = 0
    total_questions_answered: int = 0
    remaining_questions: int = 0


class ProfileResponse(BaseModel):
    id: str
    email: str
    display_name: str
    # R4: SSO support surfaces the avatar and whether a password is set.
    avatar_url: str | None = None
    has_password: bool = False
    total_quizzes: int
    total_questions_answered: int
    books: list[BookProgress]


class OAuthLinkResponse(BaseModel):
    """A linked OAuth provider with its creation timestamp."""

    provider: str
    linked_at: str


VALID_PROVIDERS = {"google", "facebook", "microsoft"}


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
        total_qs = len(book.questions) if book.questions else 0
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
                cover_url=book.cover_url,
                attempts=attempts_summary,
                best_score=best,
                total_questions_answered=answered,
                remaining_questions=max(0, total_qs - answered),
            )
        )

    return ProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        has_password=current_user.password_hash is not None,
        total_quizzes=len(attempts),
        total_questions_answered=total_answered,
        books=books,
    )


@router.get("/me/oauth-links", response_model=list[OAuthLinkResponse])
def list_oauth_links(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the OAuth providers linked to the current user."""
    links = (
        db.query(UserOAuthLink)
        .filter(UserOAuthLink.user_id == current_user.id)
        .order_by(UserOAuthLink.created_at)
        .all()
    )
    return [
        OAuthLinkResponse(provider=link.provider, linked_at=link.created_at.isoformat())
        for link in links
    ]


@router.delete("/me/oauth-links/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_oauth_provider(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unlink an OAuth provider.

    Lockout prevention (Q7): a user with no password cannot unlink their last
    remaining provider, or they would have no way to sign in.
    """
    if provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not linked.",
        )

    link = (
        db.query(UserOAuthLink)
        .filter(
            UserOAuthLink.user_id == current_user.id,
            UserOAuthLink.provider == provider,
        )
        .first()
    )
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not linked.",
        )

    remaining_links = (
        db.query(UserOAuthLink).filter(UserOAuthLink.user_id == current_user.id).count()
    )
    if current_user.password_hash is None and remaining_links <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot unlink the last authentication method. Set a password first.",
        )

    db.delete(link)
    db.commit()


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

    total_answered = sum(a.total_questions for a in attempts)
    total_qs = len(book.questions) if book.questions else 0
    remaining = max(0, total_qs - total_answered)

    return {
        "book_id": str(book.id),
        "title": book.title,
        "author": book.author,
        "cover_url": book.cover_url,
        "attempts_completed": len(attempts),
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "score": a.score,
                "total": a.total_questions,
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            }
            for a in attempts
        ],
        "total_questions": total_qs,
        "total_questions_answered": total_answered,
        "remaining_questions": remaining,
        "can_retake": remaining > 0,
    }
