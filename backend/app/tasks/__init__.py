"""Celery task definitions for background jobs.

Tasks will be registered here as background processing needs grow.
Currently, book hydration and question generation run synchronously
via the admin API (async background threads), not Celery.
"""
