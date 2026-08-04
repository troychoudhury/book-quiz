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

# Valid question_type values (DB column is VARCHAR(20))
VALID_QUESTION_TYPES = {"fact", "theme", "character", "moral", "interpretation"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}


def _sanitize_question_type(raw: str) -> str:
    """Clamp AI-generated question_type to a valid DB value."""
    cleaned = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if cleaned in VALID_QUESTION_TYPES:
        return cleaned
    # Map common AI variants
    for valid in VALID_QUESTION_TYPES:
        if valid in cleaned:
            return valid
    return "fact"


def _sanitize_difficulty(raw: str) -> str:
    """Clamp AI-generated difficulty to a valid DB value."""
    cleaned = raw.strip().lower()
    if cleaned in VALID_DIFFICULTIES:
        return cleaned
    return "medium"


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

    def fetch_chapters(
        self,
        book_title: str,
        author: str,
    ) -> list[dict]:
        """Ask the AI for a book's chapter list with brief summaries."""
        if not self.client:
            return []

        prompt = f"""Book: "{book_title}" by {author}.

List all chapters of this book in order. For each chapter provide:
- chapter number
- chapter title
- one-sentence summary of key events

Output as JSON: {{"chapters": [{{"number": 1, "title": "...", "summary": "..."}}]}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a literary expert. Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                return []
            data = json.loads(content)
            return data.get("chapters", [])
        except Exception as e:
            logger.error(f"Failed to fetch chapters for '{book_title}': {e}")
            return []

    def generate_for_book_with_chapters(
        self,
        book_title: str,
        author: str,
        age_range: str = "",
    ) -> list[GeneratedQuestion]:
        """Generate 5 questions per chapter + 5 overall book questions.

        Two API calls:
        1. Fetch chapter list from AI
        2. Generate all questions in one call per chapter + overall
        Falls back to book-level questions if AI doesn't know the chapters.
        """
        if not self.client:
            return []

        chapters = self.fetch_chapters(book_title, author)

        # Cap at 10 chapters to keep response within token limits
        if len(chapters) > 10:
            chapters = chapters[:10]

        if not chapters or len(chapters) < 2:
            logger.info(f"Few/no chapters for '{book_title}' — 30 book-level qs")
            return self.generate_for_book(book_title, author, age_range, num_questions=30)

        age_hint = f" Target age range: {age_range}." if age_range else ""
        chapter_specs = "\n".join(
            f"Ch{c['number']}: \"{c['title']}\" — {c['summary']}"
            for c in chapters
        )
        total = len(chapters) * 5 + 5

        prompt = f"""Book: "{book_title}" by {author}.{age_hint}

Chapters:
{chapter_specs}

Generate EXACTLY 5 questions per chapter + 5 overall questions. Total: {total}.
Each: 4 choices, one correct. Vary difficulty (30% easy, 40% medium, 30% hard)
and type (fact, theme, character, moral, interpretation).
Include chapter field: 0=overall, chapter number for chapter-specific.
Output JSON: {{"questions": [{{"chapter": 1, "question_text": "...", ...}}]}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=16384,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                return []
            data = json.loads(content)
            questions_raw = data if isinstance(data, list) else data.get("questions", [])

            result: list[GeneratedQuestion] = []
            for q in questions_raw:
                choices = [
                    GeneratedChoice(text=c["text"], is_correct=c["is_correct"])
                    for c in q.get("choices", [])
                ]
                ch_num = q.get("chapter", 0)
                ch_title = ""
                if ch_num > 0:
                    ch_info = next((c for c in chapters if c["number"] == ch_num), None)
                    if ch_info:
                        ch_title = ch_info["title"]
                result.append(GeneratedQuestion(
                    question_text=q["question_text"],
                    question_type=_sanitize_question_type(q.get("question_type", "fact")),
                    difficulty=_sanitize_difficulty(q.get("difficulty", "medium")),
                    choices=choices,
                    chapter=ch_num,
                    chapter_title=ch_title,
                ))

            logger.info(f"Generated {len(result)} qs for '{book_title}' ({len(chapters)}ch)")
            return result
        except Exception as e:
            logger.error(f"Generation failed for '{book_title}': {e}")
            return []

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
                        question_type=_sanitize_question_type(q.get("question_type", "fact")),
                        difficulty=_sanitize_difficulty(q.get("difficulty", "medium")),
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
        num_questions: int = 10,
    ) -> list[GeneratedQuestion]:
        """Generate multiple-choice questions for a book (no chapter data).

        The AI uses its knowledge of the book from title + author alone.
        """
        if not self.client:
            logger.warning("No API key — skipping question generation")
            return []

        prompt = self._build_book_prompt(book_title, author, age_range, num_questions)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=24576,
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
                        question_type=_sanitize_question_type(q.get("question_type", "fact")),
                        difficulty=_sanitize_difficulty(q.get("difficulty", "medium")),
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
        num_questions: int = 10,
    ) -> str:
        """Build a prompt for book-level question generation (no chapter data)."""
        age_hint = f" Target age range: {age_range}." if age_range else ""
        return f"""Book: "{book_title}" by {author}.{age_hint}

Generate {num_questions} multiple-choice questions testing a reader's understanding of this book:
- Key plot events and facts
- Main themes and messages
- Character motivations and relationships
- Moral lessons and outcomes

The questions should be answerable by someone who has read the book.
Include at least one 'all of the above' or 'none of the above' variant.
Vary difficulty: 30% easy, 40% medium, 30% hard.
"""
