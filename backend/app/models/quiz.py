"""Quiz attempt and answer models."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class QuizAttempt(Base):
    """A single quiz-taking session by a user."""

    __tablename__ = "quiz_attempts"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", "attempt_number", name="uq_user_book_attempt"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("books.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Relationships
    user = relationship("User", back_populates="quiz_attempts")
    book = relationship("Book", back_populates="quiz_attempts")
    answers = relationship("QuizAnswer", back_populates="attempt", lazy="selectin", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<QuizAttempt user={self.user_id} book={self.book_id} #{self.attempt_number}>"


class QuizAnswer(Base):
    """An individual answer within a quiz attempt."""

    __tablename__ = "quiz_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), nullable=False)
    selected_choice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("choices.id"), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    attempt = relationship("QuizAttempt", back_populates="answers")
    question = relationship("Question")
    selected_choice = relationship("Choice", foreign_keys=[selected_choice_id])

    def __repr__(self) -> str:
        return f"<QuizAnswer attempt={self.attempt_id} correct={self.is_correct}>"
