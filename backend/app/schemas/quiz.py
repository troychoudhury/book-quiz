"""Quiz-related Pydantic schemas."""
from datetime import datetime
from pydantic import BaseModel


class ChoiceResponse(BaseModel):
    id: str
    text: str
    position: int

    model_config = {"from_attributes": True}


class QuestionResponse(BaseModel):
    id: str
    question_number: int
    question_text: str
    chapter: int
    chapter_title: str | None = None
    choices: list[ChoiceResponse]

    model_config = {"from_attributes": True}


class StartQuizRequest(BaseModel):
    book_id: str


class StartQuizResponse(BaseModel):
    attempt_id: str
    questions: list[QuestionResponse]


class AnswerRequest(BaseModel):
    question_id: str
    choice_id: str


class AnswerResponse(BaseModel):
    is_correct: bool
    correct_choice_id: str
    question_number: int


class CompleteQuizRequest(BaseModel):
    email: str | None = None


class QuizResultItem(BaseModel):
    question_id: str
    question_text: str
    selected_choice: str
    correct_choice: str
    is_correct: bool
    chapter: int


class CompleteQuizResponse(BaseModel):
    attempt_id: str
    score: int
    total: int
    percentage: float
    completed_at: datetime
    results: list[QuizResultItem]
