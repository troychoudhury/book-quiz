"""Minimal HTTP health endpoint for the Celery worker Cloud Run service.

Cloud Run requires every container to bind ``$PORT`` and pass a startup
health check. A pure Celery worker has no HTTP listener, so this tiny app
runs alongside the worker process (see ``worker_entrypoint.sh``) purely so
Cloud Run keeps the instance alive and reports it healthy. It must stay
dependency-light and never import task code.
"""
from fastapi import FastAPI

app = FastAPI(title="Book Quiz Celery Worker Health")


@app.get("/")
@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "healthy"}
