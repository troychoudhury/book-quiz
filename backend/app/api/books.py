"""Book search and detail API endpoints."""
from sqlalchemy import func
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.book import Book
from app.schemas.book import BookSearchResponse, BookSummary, BookDetail

router = APIRouter(prefix="/api/v1/books", tags=["books"])


@router.get("", response_model=BookSearchResponse)
def search_books(
    q: str = Query("", description="Search query (title or ISBN)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search books by title or ISBN with fuzzy matching."""
    query = db.query(Book)

    if q.strip():
        search_term = f"%{q.strip()}%"
        query = query.filter(
            (Book.title.ilike(search_term)) | (Book.isbn == q.strip())
        )

    total = query.count()
    offset = (page - 1) * size
    books = query.order_by(Book.title).offset(offset).limit(size).all()

    items = [
        BookSummary(
            id=str(b.id),
            title=b.title,
            author=b.author,
            isbn=b.isbn,
            cover_url=b.cover_url,
            age_range_lower=b.age_range_lower,
            age_range_upper=b.age_range_upper,
            question_count=len(b.questions) if b.questions else 0,
        )
        for b in books
    ]

    return BookSearchResponse(items=items, total=total, page=page, size=size)


@router.get("/{book_id}", response_model=BookDetail)
def get_book(book_id: str, db: Session = Depends(get_db)):
    """Get detailed information about a specific book."""
    import uuid
    try:
        bid = uuid.UUID(book_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid book ID format.")

    book = db.query(Book).filter(Book.id == bid).first()
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found.")

    chapters = len(set(q.chapter for q in book.questions)) if book.questions else 0

    return BookDetail(
        id=str(book.id),
        title=book.title,
        author=book.author,
        isbn=book.isbn,
        cover_url=book.cover_url,
        age_range_lower=book.age_range_lower,
        age_range_upper=book.age_range_upper,
        question_count=len(book.questions) if book.questions else 0,
        description=book.description,
        chapters=chapters,
        total_questions=len(book.questions) if book.questions else 0,
    )
