"""User profile API endpoints."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.user import User
from app.models.book import Book
from app.models.quiz import QuizAttempt, QuizAnswer

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me/profile")
def get_profile(
    db: Session = Depends(get_db),
    # In production, user_id comes from JWT auth middleware
    # For now, we stub this — the auth middleware would inject the user
):
    """Get the authenticated user's profile with book progress."""
    # This is a stub — in production, user is resolved from JWT
    # For now, return an informative message
    return {
        "message": "Profile endpoint — requires authentication middleware to resolve user from JWT.",
        "note": "This is a stub. Full implementation requires auth dependency injection."
    }


@router.get("/me/books/{book_id}/progress")
def get_book_progress(book_id: str, db: Session = Depends(get_db)):
    """Get detailed progress for a specific book."""
    try:
        uuid.UUID(book_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid book ID.")

    return {
        "book_id": book_id,
        "message": "Book progress endpoint — stub. Full implementation requires auth middleware."
    }
