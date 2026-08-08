"""Celery application instance for background jobs.

Wired to the Redis broker/result backend configured via REDIS_URL.
Tasks (e.g. book data hydration, AI question generation) will be defined
in ``app.tasks`` as the hydration pipeline is implemented.

Start the worker with:
    celery -A app.worker worker --loglevel=info --concurrency=2
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "bookquiz",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks", "app.tasks.email_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=60 * 30,  # 30 minutes max per task (AI generation can be slow)
    task_soft_time_limit=60 * 25,
    broker_connection_retry_on_startup=True,
)

# Import tasks so Celery registers them at startup. Concrete tasks live in
# app.tasks.email_tasks (quiz results email); more land with the hydration
# milestone. The guard keeps app.tasks optional if its package ever shrinks
# to an empty placeholder again.
try:  # pragma: no cover - import guard until app.tasks exists
    from app import tasks  # noqa: F401
except ImportError:
    pass


if __name__ == "__main__":
    celery_app.start()
