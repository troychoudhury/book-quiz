"""AI-powered question generation service using OpenAI API.

Generates diverse, high-quality multiple-choice questions for
book chapters focusing on:
- Main themes
- Facts and events
- Characters and emotions
- Morals, outcomes, and interpretations
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class GeneratedChoice:
    """A single answer choice."""
    text: str
    is_correct: bool


@dataclass
class GeneratedQuestion:
    """A single AI-generated question with choices."""
    question_text: str
    question_type: str  # 'theme', 'fact', 'character', 'moral', 'interpretation'
    difficulty: str  # 'easy', 'medium', 'hard'
    choices: list[GeneratedChoice] = field(default_factory=list)
    chapter: int = 0
    chapter_title: str = ""


class QuestionGenerator:
    """Generates quiz questions using the OpenAI API."""

    SYSTEM_PROMPT = """You are an expert educational content creator specializing in
reading comprehension assessments. Generate high-quality multiple-choice
questions based on the provided book chapter information.

Rules:
1. Generate exactly 10 questions per chapter
2. Each question must have exactly 4 choices (A-D)
3. Only ONE choice should be correct
4. Distractors should be plausible but clearly wrong to someone who read carefully
5. Vary question types: theme, fact, character, moral, interpretation
6. Include 'all of the above' or 'none of the above' as choices where appropriate
7. Questions should test memory recall, comprehension, and language skills
8. Output must be valid JSON as an array of question objects

Output format (JSON array):
[
  {
    "question_text": "What is the main theme of this chapter?",
    "question_type": "theme",
    "difficulty": "medium",
    "choices": [
      {"text": "Love conquers all", "is_correct": true},
      {"text": "Power corrupts", "is_correct": false},
      {"text": "Knowledge is power", "is_correct": false},
      {"text": "Revenge is sweet", "is_correct": false}
    ]
  }
]"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini", base_url: str = ""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or None
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI | None:
        """Lazy OpenAI-compatible client — returns None if no API key configured."""
        if self._client is None and self.api_key:
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def generate_for_chapter(
        self,
        book_title: str,
        author: str,
        chapter_number: int,
        chapter_title: str,
        chapter_summary: str,
    ) -> list[GeneratedQuestion]:
        """Generate 10 multiple-choice questions for a chapter using OpenAI.

        Args:
            book_title: Title of the book
            author: Author name
            chapter_number: Chapter number
            chapter_title: Chapter title
            chapter_summary: Summary/description of chapter content

        Returns:
            List of GeneratedQuestion objects (empty if no API key or on error)
        """
        if not self.client:
            logger.warning("No OpenAI API key configured — skipping question generation")
            return []

        prompt = self._build_prompt(
            book_title, author, chapter_number, chapter_title, chapter_summary
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                logger.error("Empty response from OpenAI")
                return []

            data = json.loads(content)
            # Handle both {"questions": [...]} and [...] formats
            questions_raw = data if isinstance(data, list) else data.get("questions", [])

            result: list[GeneratedQuestion] = []
            for q in questions_raw:
                choices = [
                    GeneratedChoice(text=c["text"], is_correct=c["is_correct"])
                    for c in q.get("choices", [])
                ]
                result.append(
                    GeneratedQuestion(
                        question_text=q["question_text"],
                        question_type=q.get("question_type", "fact"),
                        difficulty=q.get("difficulty", "medium"),
                        choices=choices,
                        chapter=chapter_number,
                        chapter_title=chapter_title,
                    )
                )

            logger.info(
                f"Generated {len(result)} questions for '{book_title}' ch.{chapter_number}"
            )
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response: {e}")
            return []
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return []

    def _build_prompt(
        self,
        book_title: str,
        author: str,
        chapter_number: int,
        chapter_title: str,
        chapter_summary: str,
    ) -> str:
        """Build the prompt for the OpenAI API."""
        return f"""Book: "{book_title}" by {author}
Chapter {chapter_number}: "{chapter_title}"
Summary: {chapter_summary}

Generate 10 multiple-choice questions testing a reader's:
- Memory of key facts and events
- Comprehension of the chapter's main ideas
- Understanding of character motivations and emotions
- Interpretation of moral lessons and outcomes
- Language and vocabulary skills

Include at least one 'all of the above' or 'none of the above' choice variant.
Vary difficulty: 3 easy, 4 medium, 3 hard questions.
"""

    def generate_for_book(
        self,
        book_title: str,
        author: str,
        age_range: str = "",
    ) -> list[GeneratedQuestion]:
        """Generate 10 general multiple-choice questions for a book.

        Works without explicit chapter data — the AI has broad knowledge of
        published books and can generate reasonable questions from title +
        author alone. Questions cover themes, characters, plot, and morals.
        """
        if not self.client:
            logger.warning("No OpenAI API key configured — skipping question generation")
            return []

        prompt = self._build_book_prompt(book_title, author, age_range)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                logger.error("Empty response from OpenAI")
                return []

            data = json.loads(content)
            questions_raw = data if isinstance(data, list) else data.get("questions", [])

            result: list[GeneratedQuestion] = []
            for q in questions_raw:
                choices = [
                    GeneratedChoice(text=c["text"], is_correct=c["is_correct"])
                    for c in q.get("choices", [])
                ]
                result.append(
                    GeneratedQuestion(
                        question_text=q["question_text"],
                        question_type=q.get("question_type", "fact"),
                        difficulty=q.get("difficulty", "medium"),
                        choices=choices,
                        chapter=0,
                        chapter_title="",
                    )
                )

            logger.info(f"Generated {len(result)} questions for '{book_title}'")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response: {e}")
            return []
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return []

    def _build_book_prompt(
        self,
        book_title: str,
        author: str,
        age_range: str,
    ) -> str:
        """Build a prompt for book-level question generation (no chapter data)."""
        age_hint = f" Target age range: {age_range}." if age_range else ""
        return f"""Book: "{book_title}" by {author}.{age_hint}

Generate 10 multiple-choice questions testing a reader's understanding of this book:
- Key plot events and facts
- Main themes and messages
- Character motivations and relationships
- Moral lessons and outcomes

The questions should be answerable by someone who has read the book.
Include at least one 'all of the above' or 'none of the above' variant.
Vary difficulty: 3 easy, 4 medium, 3 hard.
"""
