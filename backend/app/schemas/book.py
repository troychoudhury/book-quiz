"""Book-related Pydantic schemas."""
from pydantic import BaseModel


class BookSummary(BaseModel):
    """Summary of a book for list/search views."""
    id: str
    title: str
    author: str
    isbn: str | None = None
    cover_url: str | None = None
    age_range_lower: int | None = None
    age_range_upper: int | None = None
    question_count: int = 0

    model_config = {"from_attributes": True}


class BookDetail(BookSummary):
    """Detailed book information."""
    description: str | None = None
    chapters: int = 0
    total_questions: int = 0

    model_config = {"from_attributes": True}


class BookSearchResponse(BaseModel):
    """Paginated search response."""
    items: list[BookSummary]
    total: int
    page: int
    size: int
