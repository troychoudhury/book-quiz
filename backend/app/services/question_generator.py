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
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GeneratedQuestion:
    """A single AI-generated question with choices."""
    question_text: str
    question_type: str  # 'theme', 'fact', 'character', 'moral', 'interpretation'
    difficulty: str  # 'easy', 'medium', 'hard'
    choices: list[dict]  # [{"text": "...", "is_correct": bool}, ...]
    chapter: int
    chapter_title: str


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
5. Vary question types: main themes, facts/events, characters/emotions, morals/interpretations
6. Include 'all of the above' or 'none of the above' as choices where appropriate
7. Questions should test memory recall, comprehension, and language skills
8. Output must be valid JSON matching the specified schema
"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def generate_for_chapter(
        self,
        book_title: str,
        author: str,
        chapter_number: int,
        chapter_title: str,
        chapter_summary: str,
    ) -> list[GeneratedQuestion]:
        """Generate questions for a single chapter.

        This is a STUB — implementation would call OpenAI API with
        a carefully crafted prompt including the chapter summary.
        """
        logger.info(
            f"Generating questions for '{book_title}' ch.{chapter_number} (stub)"
        )
        return []  # Stub

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
"""
