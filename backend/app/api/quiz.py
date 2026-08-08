"""Quiz API endpoints."""
import random
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_optional_current_user
from app.models.book import Book
from app.models.question import Question, Choice
from app.models.quiz import QuizAttempt, QuizAnswer
from app.models.user import User
from app.schemas.quiz import (
    StartQuizRequest,
    StartQuizResponse,
    QuestionResponse,
    ChoiceResponse,
    AnswerRequest,
    AnswerResponse,
    CompleteQuizRequest,
    CompleteQuizResponse,
    QuizResultItem,
)

router = APIRouter(prefix="/api/v1/quizzes", tags=["quizzes"])

logger = structlog.get_logger()

QUIZ_QUESTION_COUNT = 10


def _enqueue_results_email(
    email: str,
    score: int,
    total: int,
    percentage: float,
    results: list[dict],
) -> None:
    """Enqueue the quiz results email Celery task (best-effort).

    Imported lazily to avoid a circular import with app.worker. Any failure
    (e.g. Redis down) is logged and swallowed — email must never block or
    break quiz completion.
    """
    try:
        from app.tasks.email_tasks import send_quiz_results_email

        send_quiz_results_email.delay(email, score, total, percentage, results)
        logger.info(
            "quiz.results_email_enqueued",
            email=email,
            score=score,
            total=total,
        )
    except Exception:
        logger.exception(
            "quiz.results_email_enqueue_failed",
            email=email,
            score=score,
            total=total,
        )


@router.post("/start", response_model=StartQuizResponse, status_code=status.HTTP_201_CREATED)
def start_quiz(
    request: StartQuizRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Start a new quiz for a book. Selects 10 random unanswered questions.

    For authenticated users, previously answered questions (across all their
    attempts for this book) are excluded so retakes always surface fresh
    questions. Guests get a random selection.
    """
    try:
        book_id = uuid.UUID(request.book_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid book ID.")

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found.")

    all_questions = db.query(Question).filter(Question.book_id == book_id).all()
    if not all_questions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No questions available for this book.")

    # Exclude questions the user has already answered (if authenticated).
    answered_ids: set[uuid.UUID] = set()
    if current_user is not None:
        answered_rows = (
            db.query(QuizAnswer.question_id)
            .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
            .filter(QuizAttempt.user_id == current_user.id)
            .distinct()
            .all()
        )
        answered_ids = {row[0] for row in answered_rows}

    available = [q for q in all_questions if q.id not in answered_ids]
    if not available:
        # User has answered every question; offer a full retake over all questions.
        available = all_questions

    selected = random.sample(available, min(QUIZ_QUESTION_COUNT, len(available)))

    # Determine attempt number for this user/book.
    attempt_number = 1
    if current_user is not None:
        last_attempt = (
            db.query(QuizAttempt)
            .filter(
                QuizAttempt.user_id == current_user.id,
                QuizAttempt.book_id == book_id,
            )
            .order_by(QuizAttempt.attempt_number.desc())
            .first()
        )
        if last_attempt is not None:
            attempt_number = last_attempt.attempt_number + 1

    # Build responses WITHOUT mutating stored choice positions. The canonical
    # A–D ordering in the DB must never be rewritten by a quiz start.
    question_responses = []
    for i, question in enumerate(selected):
        shuffled = list(question.choices)
        random.shuffle(shuffled)
        question_responses.append(
            QuestionResponse(
                id=str(question.id),
                question_number=i + 1,
                question_text=question.question_text,
                chapter=question.chapter,
                chapter_title=question.chapter_title,
                choices=[
                    ChoiceResponse(id=str(c.id), text=c.choice_text, position=idx)
                    for idx, c in enumerate(shuffled)
                ],
            )
        )

    attempt = QuizAttempt(
        user_id=current_user.id if current_user else None,
        book_id=book_id,
        total_questions=len(selected),
        attempt_number=attempt_number,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return StartQuizResponse(attempt_id=str(attempt.id), questions=question_responses)


@router.post("/{attempt_id}/answer", response_model=AnswerResponse)
def answer_question(
    attempt_id: str,
    request: AnswerRequest,
    db: Session = Depends(get_db),
):
    """Submit an answer for a question in an active quiz attempt."""
    try:
        aid = uuid.UUID(attempt_id)
        qid = uuid.UUID(request.question_id)
        cid = uuid.UUID(request.choice_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format.")

    attempt = db.query(QuizAttempt).filter(QuizAttempt.id == aid).first()
    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found.")
    if attempt.completed_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quiz already completed.")

    question = db.query(Question).filter(Question.id == qid).first()
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found.")

    # The question must belong to the attempt's book.
    if question.book_id != attempt.book_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question does not belong to this quiz attempt.",
        )

    # The choice must belong to this question.
    choice = db.query(Choice).filter(Choice.id == cid, Choice.question_id == qid).first()
    if not choice:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choice does not belong to this question.",
        )

    # Prevent duplicate answers for the same question within this attempt.
    already_answered = (
        db.query(QuizAnswer)
        .filter(QuizAnswer.attempt_id == aid, QuizAnswer.question_id == qid)
        .first()
    )
    if already_answered:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question already answered in this attempt.",
        )

    is_correct = choice.is_correct

    answer = QuizAnswer(
        attempt_id=aid,
        question_id=qid,
        selected_choice_id=cid,
        is_correct=is_correct,
    )
    db.add(answer)
    db.commit()

    answered_count = db.query(QuizAnswer).filter(QuizAnswer.attempt_id == aid).count()

    return AnswerResponse(
        is_correct=is_correct,
        correct_choice_id=str(choice.id) if is_correct else "",
        question_number=answered_count,
    )


@router.post("/{attempt_id}/complete", response_model=CompleteQuizResponse)
def complete_quiz(
    attempt_id: str,
    request: CompleteQuizRequest | None = None,
    db: Session = Depends(get_db),
):
    """Complete a quiz attempt and calculate final score."""
    try:
        aid = uuid.UUID(attempt_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attempt ID.")

    attempt = db.query(QuizAttempt).filter(QuizAttempt.id == aid).first()
    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found.")
    if attempt.completed_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quiz already completed.")

    answers = db.query(QuizAnswer).filter(QuizAnswer.attempt_id == aid).all()
    if not answers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot complete a quiz with no answers.",
        )

    score = sum(1 for a in answers if a.is_correct)
    total = len(answers)

    attempt.score = score
    attempt.completed_at = datetime.now(timezone.utc)
    attempt.total_questions = total
    db.commit()
    db.refresh(attempt)

    results = []
    for a in answers:
        q = db.query(Question).filter(Question.id == a.question_id).first()
        correct_c = (
            db.query(Choice)
            .filter(Choice.question_id == a.question_id, Choice.is_correct.is_(True))
            .first()
        )
        selected_c = db.query(Choice).filter(Choice.id == a.selected_choice_id).first()
        results.append(
            QuizResultItem(
                question_id=str(a.question_id),
                question_text=q.question_text if q else "",
                selected_choice=selected_c.choice_text if selected_c else "",
                correct_choice=correct_c.choice_text if correct_c else "",
                is_correct=a.is_correct,
                chapter=q.chapter if q else 0,
            )
        )

    percentage = round((score / total * 100) if total > 0 else 0, 1)

    # Best-effort results email — never blocks or breaks completion.
    if request is not None and request.email:
        results_data = [item.model_dump() for item in results]
        _enqueue_results_email(request.email, score, total, percentage, results_data)

    return CompleteQuizResponse(
        attempt_id=str(attempt.id),
        score=score,
        total=total,
        percentage=percentage,
        completed_at=attempt.completed_at,
        results=results,
    )
