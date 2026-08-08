"""Quiz results email — build HTML content and send via SMTP.

Best-effort only: if SMTP is not configured (empty ``SMTP_PASSWORD``) the
email is skipped with a warning. Sending must NEVER block or break the quiz
completion flow, so failures are logged and swallowed by callers.
"""
import smtplib
from email.message import EmailMessage
from html import escape

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()


def build_quiz_results_email(
    score: int,
    total: int,
    percentage: float,
    results: list[dict],
    recipient_email: str,
) -> tuple[str, str]:
    """Build (subject, html) for a quiz results email.

    ``results`` is a list of dicts with keys: question_id, question_text,
    selected_choice, correct_choice, is_correct, chapter.
    """
    subject = f"Your Book Quiz results: {score}/{total} ({percentage:g}%)"

    rows = []
    for i, item in enumerate(results, start=1):
        question_text = escape(item.get("question_text", ""))
        chapter = escape(str(item.get("chapter", "")))
        selected = escape(item.get("selected_choice", ""))
        correct = escape(item.get("correct_choice", ""))
        is_correct = bool(item.get("is_correct"))
        status = "✅ Correct" if is_correct else "❌ Incorrect"
        status_class = "correct" if is_correct else "incorrect"
        rows.append(
            f"""
            <tr class="{status_class}">
              <td class="num">{i}</td>
              <td>
                <div class="q">{question_text}</div>
                <div class="meta">Chapter {chapter}</div>
                <div class="meta">Your answer: {selected}</div>
                <div class="meta">Correct answer: {correct}</div>
              </td>
              <td class="status">{status}</td>
            </tr>"""
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, Helvetica, sans-serif; color: #222; margin: 0; padding: 24px; }}
    .card {{ max-width: 640px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }}
    .header {{ background: #1a3d7c; color: #fff; padding: 24px; }}
    .header h1 {{ margin: 0; font-size: 22px; }}
    .summary {{ padding: 24px; background: #f6f8fb; text-align: center; }}
    .summary .score {{ font-size: 40px; font-weight: bold; }}
    .summary .detail {{ color: #555; margin-top: 8px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; background: #eef1f6; padding: 10px 16px; }}
    td {{ padding: 12px 16px; border-top: 1px solid #eee; vertical-align: top; }}
    .q {{ font-weight: bold; }}
    .meta {{ color: #666; font-size: 13px; margin-top: 4px; }}
    .status {{ white-space: nowrap; font-weight: bold; }}
    .correct .status {{ color: #1a7f37; }}
    .incorrect .status {{ color: #b42318; }}
    .footer {{ padding: 16px 24px; color: #888; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header"><h1>Your Book Quiz Results</h1></div>
    <div class="summary">
      <div class="score">{score}/{total}</div>
      <div class="detail">You scored {percentage:g}% on this quiz.</div>
    </div>
    <table>
      <thead><tr><th style="width:36px;">#</th><th>Question</th><th>Result</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    <div class="footer">Sent by Book Quiz — keep reading!</div>
  </div>
</body>
</html>"""

    return subject, html


def send_email(recipient: str, subject: str, html: str) -> None:
    """Send an HTML email over SMTP (STARTTLS). No-op when SMTP is unconfigured.

    Never raises: SMTP failures are logged and swallowed so callers (e.g. the
    quiz completion flow) are never blocked by email problems.
    """
    settings = get_settings()
    if not settings.smtp_password:
        logger.warning(
            "email.send_skipped_smtp_not_configured",
            recipient=recipient,
            subject=subject,
            hint="Set SMTP_PASSWORD to enable quiz result emails.",
        )
        return

    if not settings.smtp_from_email:
        logger.warning(
            "email.send_skipped_from_email_not_configured",
            hint="Set SMTP_FROM_EMAIL (SMTP_PASSWORD is set but the sender address is empty).",
        )
        return

    try:
        from_email = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = recipient
        msg.set_content(html, subtype="html")

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info(
            "email.send_succeeded",
            recipient=recipient,
            subject=subject,
        )
    except Exception:
        # Best-effort only — a failed email must never break the caller.
        logger.exception(
            "email.send_failed",
            recipient=recipient,
            subject=subject,
            host=settings.smtp_host,
            port=settings.smtp_port,
        )
