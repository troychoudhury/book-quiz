"""Celery task for sending quiz results emails.

Registered via the ``include`` list in ``app.worker``; the worker process
imports this module and registers ``send_quiz_results_email`` with the
``bookquiz`` Celery app.
"""
import structlog

from app.services.email_service import build_quiz_results_email, send_email
from app.worker import celery_app

logger = structlog.get_logger()


@celery_app.task(name="email.send_quiz_results_email")
def send_quiz_results_email(
    recipient_email: str,
    score: int,
    total: int,
    percentage: float,
    results: list[dict],
) -> None:
    """Build and send the quiz results email (best-effort, never raises)."""
    subject, html = build_quiz_results_email(
        score=score,
        total=total,
        percentage=percentage,
        results=results,
        recipient_email=recipient_email,
    )
    logger.info(
        "email.quiz_results_task_started",
        recipient=recipient_email,
        score=score,
        total=total,
    )
    send_email(recipient_email, subject, html)
