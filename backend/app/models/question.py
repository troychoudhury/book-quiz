"""Question and Choice models."""
from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
import uuid


class Question(Base):
    """A quiz question tied to a book chapter."""

    __tablename__ = "questions"

    book_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("books.id"), nullable=False, index=True)
    chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), default="multiple_choice")
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")

    # Relationships
    book = relationship("Book", back_populates="questions")
    choices = relationship("Choice", back_populates="question", lazy="selectin", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Question {self.id} ch.{self.chapter}>"


class Choice(Base):
    """A multiple-choice answer option."""

    __tablename__ = "choices"

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    choice_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # Relationships
    question = relationship("Question", back_populates="choices")

    def __repr__(self) -> str:
        return f"<Choice {'✓' if self.is_correct else '✗'} pos={self.position}>"
