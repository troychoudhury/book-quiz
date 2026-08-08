"""Unit tests for the quiz results email service (build + SMTP send)."""
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-acceptance-tests")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.services.email_service import build_quiz_results_email, send_email

settings = get_settings()

SAMPLE_RESULTS = [
    {
        "question_id": "q1",
        "question_text": "Who wrote the Odyssey?",
        "selected_choice": "Homer",
        "correct_choice": "Homer",
        "is_correct": True,
        "chapter": 1,
    },
    {
        "question_id": "q2",
        "question_text": "What color is the sky?",
        "selected_choice": "Green",
        "correct_choice": "Blue",
        "is_correct": False,
        "chapter": 2,
    },
]


class TestBuildQuizResultsEmail:
    def test_returns_subject_with_score(self):
        """Subject includes the score summary."""
        subject, html = build_quiz_results_email(3, 5, 60.0, SAMPLE_RESULTS, "a@example.com")
        assert "3/5" in subject
        assert "60%" in subject
        assert "60.0%" not in subject  # trailing .0 trimmed

    def test_html_contains_question_breakdown(self):
        """HTML includes per-question text, chapter, and choices."""
        _, html = build_quiz_results_email(3, 5, 60.0, SAMPLE_RESULTS, "a@example.com")
        assert "Who wrote the Odyssey?" in html
        assert "Chapter 1" in html
        assert "Homer" in html  # selected + correct choice
        assert "Green" in html  # incorrect selected choice
        assert "Correct" in html
        assert "Incorrect" in html

    def test_html_escapes_user_content(self):
        """Question text / choices are HTML-escaped to prevent injection."""
        malicious = [{
            "question_id": "q1",
            "question_text": "<script>alert('xss')</script>",
            "selected_choice": "<img src=x onerror=alert(1)>",
            "correct_choice": "Safe",
            "is_correct": False,
            "chapter": 1,
        }]
        _, html = build_quiz_results_email(0, 1, 0.0, malicious, "a@example.com")
        assert "<script>alert('xss')</script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_results_still_renders(self):
        """A quiz with no results still produces valid subject/html."""
        subject, html = build_quiz_results_email(0, 0, 0.0, [], "a@example.com")
        assert "0/0" in subject
        assert "<html" in html


class TestSendEmail:
    @pytest.fixture(autouse=True)
    def _configure_smtp(self, monkeypatch):
        """Point SMTP settings at a test server for the duration of the test."""
        monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
        monkeypatch.setattr(settings, "smtp_port", 587)
        monkeypatch.setattr(settings, "smtp_user", "quiz-bot")
        monkeypatch.setattr(settings, "smtp_password", "secret")
        monkeypatch.setattr(settings, "smtp_from_email", "quiz@example.com")
        monkeypatch.setattr(settings, "smtp_from_name", "Book Quiz")

    @patch("app.services.email_service.smtplib.SMTP")
    def test_sends_via_smtp_starttls_login(self, mock_smtp_class):
        """Configured SMTP sends the message over STARTTLS with login."""
        server = MagicMock()
        server.__enter__.return_value = server  # `with SMTP(...) as server:` binds this mock
        mock_smtp_class.return_value = server

        send_email("reader@example.com", "Subject line", "<html><body>Hi</body></html>")

        mock_smtp_class.assert_called_once_with("smtp.test.local", 587, timeout=30)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("quiz-bot", "secret")
        server.send_message.assert_called_once()
        sent = server.send_message.call_args[0][0]
        assert sent["From"] == "Book Quiz <quiz@example.com>"
        assert sent["To"] == "reader@example.com"
        assert sent["Subject"] == "Subject line"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_empty_password_skips_send_without_error(self, mock_smtp_class, monkeypatch):
        """Empty SMTP_PASSWORD degrades gracefully — no send, no crash."""
        monkeypatch.setattr(settings, "smtp_password", "")

        send_email("reader@example.com", "Subject", "<html></html>")

        mock_smtp_class.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_missing_from_email_skips_send(self, mock_smtp_class, monkeypatch):
        """Password set but SMTP_FROM_EMAIL empty → skip with warning, no crash."""
        monkeypatch.setattr(settings, "smtp_from_email", "")

        send_email("reader@example.com", "Subject", "<html></html>")

        mock_smtp_class.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_hostile_recipient_newline_does_not_raise(self, mock_smtp_class):
        """A newline in the recipient must not raise out of send_email
        (header injection attempt) — it is swallowed like any SMTP failure."""
        send_email("victim@example.com\r\nBcc: attacker@example.com", "Subject", "<html></html>")
        # Must not raise; SMTP send was attempted or the header error was swallowed.
        assert True

    @patch("app.services.email_service.smtplib.SMTP")
    def test_smtp_failure_is_swallowed(self, mock_smtp_class):
        """SMTP errors are logged, not raised — best-effort sending."""
        mock_smtp_class.side_effect = ConnectionError("smtp down")

        # Must not raise.
        send_email("reader@example.com", "Subject", "<html></html>")
