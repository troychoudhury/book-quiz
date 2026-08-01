"""Quiz API endpoints."""
import uuid
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.book import Book
from app.models.question import Question, Choice
from app.models.quiz import QuizAttempt, QuizAnswer
from app.models.user import User
from app.schemas.quiz import (
    StartQuizRequest, StartQuizResponse, QuestionResponse, ChoiceResponse,
    AnswerRequest, AnswerResponse, CompleteQuizRequest, CompleteQuizResponse,
    QuizResultItem,
)

router = APIRouter(prefix="/api/v1/quizzes", tags=["quizzes"])


def _get_or_create_user(db: Session, user_id: str | None) -> User | None:
    if not user_id:
        return None
    try:
        return db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    except ValueError:
        return None


@router.post("/start", response_model=StartQuizResponse, status_code=status.HTTP_201_CREATED)
def start_quiz(request: StartQuizRequest, db: Session = Depends(get_db)):
    """Start a new quiz for a book. Selects 10 random unanswered questions."""
    try:
        book_id = uuid.UUID(request.book_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid book ID.")

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found.")

    # Get all questions for the book
    all_questions = db.query(Question).filter(Question.book_id == book_id).all()
    if not all_questions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No questions available for this book.")

    # Select 10 random questions (or all if fewer)
    selected = random.sample(all_questions, min(10, len(all_questions)))

    # Shuffle choices for each question
    question_responses = []
    for i, question in enumerate(selected):
        choices = list(question.choices)
        random.shuffle(choices)
        # Re-index positions after shuffle
        for j, c in enumerate(choices):
            c.position = j
        question_responses.append(QuestionResponse(
            id=str(question.id),
            question_number=i + 1,
            question_text=question.question_text,
            chapter=question.chapter,
            chapter_title=question.chapter_title,
            choices=[
                ChoiceResponse(id=str(c.id), text=c.choice_text, position=c.position)
                for c in choices
            ],
        ))

    # Create attempt record
    attempt = QuizAttempt(
        user_id=None,  # Guest attempt; linked later if user authenticates
        book_id=book_id,
        total_questions=len(selected),
        attempt_number=1,
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

    correct_choice = next((c for c in question.choices if c.is_correct), None)
    is_correct = str(correct_choice.id) == request.choice_id if correct_choice else False

    # Record the answer
    answer = QuizAnswer(
        attempt_id=aid,
        question_id=qid,
        selected_choice_id=cid,
        is_correct=is_correct,
    )
    db.add(answer)
    db.commit()

    # Find question number in this attempt
    answered_count = db.query(QuizAnswer).filter(QuizAnswer.attempt_id == aid).count()

    return AnswerResponse(
        is_correct=is_correct,
        correct_choice_id=str(correct_choice.id) if correct_choice else "",
        question_number=answered_count,
    )


@router.post("/{attempt_id}/complete", response_model=CompleteQuizResponse)
def complete_quiz(
    attempt_id: str,
    request: CompleteQuizRequest = CompleteQuizRequest(),
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
    score = sum(1 for a in answers if a.is_correct)
    total = len(answers)

    attempt.score = score
    attempt.completed_at = datetime.now(timezone.utc)
    attempt.total_questions = total
    db.commit()
    db.refresh(attempt)

    # Build result items
    results = []
    for a in answers:
        q = db.query(Question).filter(Question.id == a.question_id).first()
        correct_c = db.query(Choice).filter(Choice.question_id == a.question_id, Choice.is_correct == True).first()
        selected_c = db.query(Choice).filter(Choice.id == a.selected_choice_id).first()
        results.append(QuizResultItem(
            question_id=str(a.question_id),
            question_text=q.question_text if q else "",
            selected_choice=selected_c.choice_text if selected_c else "",
            correct_choice=correct_c.choice_text if correct_c else "",
            is_correct=a.is_correct,
            chapter=q.chapter if q else 0,
        ))

    return CompleteQuizResponse(
        attempt_id=str(attempt.id),
        score=score,
        total=total,
        percentage=round((score / total * 100) if total > 0 else 0, 1),
        completed_at=attempt.completed_at,
        results=results,
    )
