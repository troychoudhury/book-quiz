"""Book search and detail API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, load_only, noload

from app.core.database import get_db
from app.core.security import limiter
from app.models.book import Book
from app.schemas.book import (
    AutocompleteResponse,
    AutocompleteSuggestion,
    BookDetail,
    BookSearchResponse,
    BookSummary,
)

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
        query = query.filter((Book.title.ilike(search_term)) | (Book.isbn == q.strip()))

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


@router.get("/autocomplete", response_model=AutocompleteResponse)
# L2: Uses in-memory storage; migrate to Redis for multi-process deployments.
@limiter.limit("30/minute")
def autocomplete_books(
    request: Request,
    response: Response,
    q: str = Query(
        ...,
        min_length=1,
        max_length=200,
        description="Autocomplete query (min 2 characters after trimming)",
    ),
    db: Session = Depends(get_db),
):
    """Return up to 50 book suggestions ranked by title/author similarity.

    Ranking uses GREATEST(similarity(title, q), similarity(author, q)) so a
    strong match on either field surfaces (blocker B1). Requires PostgreSQL
    pg_trgm; SQLite uses a LIKE fallback that diverges on similarity ranking
    (acknowledged limitation N6). Queries shorter than 2 characters
    short-circuit without a DB hit.
    """
    # L3: private, short-lived cache — browsers may reuse, proxies must not.
    response.headers["Cache-Control"] = "private, max-age=30"

    trimmed = q.strip()
    if len(trimmed) < 2:
        return AutocompleteResponse(suggestions=[])

    title_similarity = func.similarity(Book.title, trimmed)
    author_similarity = func.similarity(Book.author, trimmed)

    # M3: selectin-eager `questions`/`quiz_attempts` are irrelevant here and
    # caused 3 SELECTs per request; load only the suggestion columns.
    books = (
        db.query(Book)
        .options(
            load_only(Book.id, Book.title, Book.author, Book.cover_url),
            noload(Book.questions),
            noload(Book.quiz_attempts),
        )
        .filter((title_similarity > 0) | (author_similarity > 0))
        .order_by(
            func.greatest(title_similarity, author_similarity).desc(), Book.title.asc()
        )
        .limit(50)
        .all()
    )

    return AutocompleteResponse(
        suggestions=[
            AutocompleteSuggestion(
                id=str(book.id),
                title=book.title,
                author=book.author,
                cover_url=book.cover_url,
            )
            for book in books
        ]
    )


@router.get("/{book_id}", response_model=BookDetail)
def get_book(book_id: str, db: Session = Depends(get_db)):
    """Get detailed information about a specific book."""
    import uuid

    try:
        bid = uuid.UUID(book_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid book ID format."
        )

    book = db.query(Book).filter(Book.id == bid).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Book not found."
        )

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
