"""Book model for quiz subjects."""
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import INT4RANGE
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Book(Base):
    """A book available for quizzing."""

    __tablename__ = "books"

    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(300), nullable=False)
    isbn: Mapped[str] = mapped_column(String(13), unique=True, nullable=True, index=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    age_range_lower: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_range_upper: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    questions = relationship("Question", back_populates="book", lazy="selectin")
    quiz_attempts = relationship("QuizAttempt", back_populates="book", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Book {self.title}>"
