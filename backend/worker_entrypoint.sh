#!/usr/bin/env bash
#==============================================================================
# worker_entrypoint.sh — Cloud Run Celery worker entrypoint
#==============================================================================
# Cloud Run requires the container to bind $PORT and pass a startup health
# check. A pure Celery worker has no HTTP listener, so this entrypoint runs
# a tiny uvicorn health app in the background and the Celery worker in the
# foreground. When the worker exits (e.g. fatal error), the container stops
# and Cloud Run restarts it.
#
# Deploy flags that matter (see lib/dev-deploy.sh deploy_worker):
#   --no-cpu-throttling   CPU is always-on so background work is not starved
#   --min-instances=1     keep an instance alive to drain the queue
#   --max-instances=1     one consumer is enough for this app
#==============================================================================
set -euo pipefail

PORT="${PORT:-8080}"

# Health listener in the background — dies with the container.
python -m uvicorn app.worker_health:app --host 0.0.0.0 --port "$PORT" &
HEALTH_PID=$!
trap 'kill "$HEALTH_PID" 2>/dev/null || true' EXIT

# Worker in the foreground — when it exits, the container stops.
exec celery -A app.worker worker --loglevel=info --concurrency=1
