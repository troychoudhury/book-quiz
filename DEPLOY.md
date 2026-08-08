# Deploying Book Quiz to Google Cloud (Cloud Run + Firebase)

## Architecture

```
┌─────────────────────┐     ┌──────────────────┐     ┌────────────────┐
│  Firebase Hosting   │────▶│   Cloud Run       │────▶│   Cloud SQL     │
│  (React SPA)        │     │   (FastAPI)        │     │   (PostgreSQL)   │
│  book-quiz.web.app  │     │   api-xxxx.run.app │     │                  │
└─────────────────────┘     └──────────────────┘     └────────────────┘
                                     │
                                     ▼
                            ┌──────────────────┐
                            │   Upstash Redis   │
                            │   (serverless)    │
                            └──────────────────┘
```

## Prerequisites

1. Google Cloud project with billing enabled (Blaze plan)
2. [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated
3. [Firebase CLI](https://firebase.google.com/docs/cli): `npm i -g firebase-tools`
4. Docker installed (for building images locally)

---

## 1. Database — Cloud SQL

```bash
# Create PostgreSQL instance (smallest for dev: db-f1-micro ~$9/mo)
gcloud sql instances create book-quiz-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=us-central1

# Create database
gcloud sql databases create bookquiz --instance=book-quiz-db

# Generate and save password
DB_PASS=$(openssl rand -base64 24 | tr -d '\n')

# Create user
gcloud sql users create bookquiz \
  --instance=book-quiz-db \
  --password="$DB_PASS"

# Get connection name (needed for Cloud Run)
CONNECTION_NAME=$(gcloud sql instances describe book-quiz-db \
  --format='value(connectionName)')
echo "Connection name: $CONNECTION_NAME"
```

---

## 2. Redis — Upstash (recommended)

Cloud Run cannot connect directly to Cloud Memorystore without a VPC connector
(~$8/mo extra). **Upstash Redis** gives you a public URL that works out of the
box, with a free tier sufficient for dev/early production.

1. Sign up at **https://console.upstash.com** (GitHub/Google login)
2. Create a Redis database → pick a region close to `us-central1`
3. Copy the **`UPSTASH_REDIS_URL`** from the dashboard:

```
redis://default:<password>@<host>.upstash.io:6379
```

> **Note:** You only need the Redis URL, not the REST API token. The backend
> uses `redis-py` with the native Redis protocol over TCP.

### Celery worker (required for email + background tasks)

The backend uses Celery (broker = Redis) for background jobs, including the
quiz-results email. A Celery worker must be running somewhere to consume the
queue:

- **Local dev:** `./dev up` starts a Celery worker automatically (both modes).
- **Fly.io:** `fly.toml` already defines a `worker` process — nothing to do.
- **Cloud Run (current production):** the `book-quiz-api` service runs only
  uvicorn. You must deploy a separate long-running worker (e.g. a Cloud Run
  service with `--min-instances 1` running `celery -A app.worker worker`, a
  Compute Engine VM, or a small Kubernetes/Cloud Run Job setup). Until a
  worker is running, emails are queued but never sent.

Upstash officially supports Celery as a broker (blocking pops work over the
native protocol), so no special Redis config is needed.

If you prefer Cloud Memorystore (for sub-millisecond latency at ~$35+/mo):

```bash
gcloud redis instances create book-quiz-redis \
  --size=1 --region=us-central1 --redis-version=redis_7_x

gcloud compute networks vpc-access connectors create book-quiz-connector \
  --region=us-central1 --range=10.8.0.0/28

# Get the Redis host IP
REDIS_HOST=$(gcloud redis instances describe book-quiz-redis \
  --region=us-central1 --format='value(host)')

# Add --vpc-connector=book-quiz-connector to the deploy command below
```

---

## 3. Environment Configuration — `.env.production`

Copy `.env.example` to `.env.production` and fill in the values:

```bash
cp .env.example .env.production
```

Generate secrets:

```bash
echo "JWT_SECRET_KEY:  $(openssl rand -hex 32)"
echo "ADMIN_API_KEY:   $(openssl rand -base64 32 | tr -d '\n')"
```

Replace these placeholders in `.env.production`:

| Variable | How to get it |
|----------|---------------|
| `DATABASE_URL` | `postgresql://bookquiz:<password>@/bookquiz?host=/cloudsql/<connection-name>` |
| `REDIS_URL` | From Upstash dashboard: `redis://default:<password>@<host>.upstash.io:6379` |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `ADMIN_API_KEY` | `openssl rand -base64 32 \| tr -d '\n'` |
| `OPENAI_API_KEY` | OpenAI dashboard → API keys |
| `ENVIRONMENT` | Set to `production` |
| `OAUTH_REDIRECT_DOMAIN` | Your Cloud Run URL (after first deploy) |
| `OAUTH_FRONTEND_CALLBACK_URL` | `https://book-quiz.web.app/auth/callback` |

### OAuth providers (optional)

Each provider is optional — leave `CLIENT_ID` empty to disable the login button.

**Google:** https://console.cloud.google.com/apis/credentials → Create OAuth client ID (Web application).
Add `{OAUTH_REDIRECT_DOMAIN}/api/v1/auth/oauth/google/callback` as an authorized redirect URI.

**Facebook:** https://developers.facebook.com/apps → Add "Facebook Login" product.
Add `{OAUTH_REDIRECT_DOMAIN}/api/v1/auth/oauth/facebook/callback`.

**Microsoft:** https://portal.azure.com → Microsoft Entra ID → App registrations.
Add `{OAUTH_REDIRECT_DOMAIN}/api/v1/auth/oauth/microsoft/callback`.

---

## 4. Deploy

The project uses a **pre-built image workflow**: build the Docker image locally,
test the same artifact, then push and deploy. This ensures the exact image you
test is what reaches production.

### Quick deploy (both backend + frontend)

```bash
./dev deploy
```

### Deploy individual components

```bash
./dev deploy backend              # Deploy backend to Cloud Run
./dev deploy frontend             # Deploy frontend to Firebase Hosting
./dev deploy --staging backend    # Deploy to staging service
```

### Manual deploy (what `dev deploy` does under the hood)

**Backend — Cloud Run:**

```bash
# Build
docker build -f Dockerfile.cloudrun -t gcr.io/<project>/book-quiz-api .

# Push
docker push gcr.io/<project>/book-quiz-api

# Deploy
gcloud run deploy book-quiz-api \
  --image gcr.io/<project>/book-quiz-api \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --add-cloudsql-instances=<connection-name> \
  --set-env-vars="$(grep -vE '^(#|$|POSTGRES_DB=|POSTGRES_USER=|POSTGRES_PORT=|BACKEND_PORT=|FRONTEND_PORT=|DEBUG=)' .env.production | tr '\n' ',' | sed 's/,$//')"
```

**Frontend — Firebase Hosting:**

```bash
cd frontend
VITE_API_URL=<cloud-run-url> npm run build
cd ..
firebase deploy --only hosting
```

---

## 5. Local dev → CI → production flow

The pre-built image workflow enables a consistent pipeline where the same image
artifact moves through environments:

```
docker build -f Dockerfile.cloudrun -t book-quiz-api .
  │
  ├─► Local dev:  docker run --env-file .env book-quiz-api
  │       Run end-to-end tests against localhost:8000
  │
  ├─► CI:  gcloud builds submit --tag gcr.io/.../book-quiz-api:sha
  │       gcloud run deploy book-quiz-api-staging --image gcr.io/.../book-quiz-api:sha
  │       Run acceptance tests against staging URL
  │
  └─► Production:  gcloud run deploy book-quiz-api --image gcr.io/.../book-quiz-api:sha
          Same image digest — the exact bytes that passed tests
```

### Dev tooling quick reference

```bash
./dev build              # Build production images locally
./dev build backend      # Build backend only (Dockerfile.cloudrun)
./dev build frontend     # Build frontend only (frontend/Dockerfile)
./dev test               # Run all tests
./dev test backend       # Backend tests only (pytest)
./dev test --e2e         # End-to-end tests only (Playwright)
./dev deploy             # Deploy both to production
./dev deploy --staging   # Deploy to staging
```

---

## 6. Post-Deploy Verification

```bash
# Health check
curl https://<cloud-run-url>/api/v1/health

# Frontend
curl https://book-quiz.web.app

# Database connectivity
curl https://<cloud-run-url>/api/v1/books/autocomplete?q=harry
```

---

## Environment Variables Reference

| Variable | Where | Description |
|----------|-------|-------------|
| `VITE_API_URL` | Frontend build | Cloud Run service URL |
| `DATABASE_URL` | Cloud Run | Cloud SQL connection string |
| `JWT_SECRET_KEY` | Cloud Run | 64-char random hex string |
| `ADMIN_API_KEY` | Cloud Run | Admin API key |
| `REDIS_URL` | Cloud Run | Redis connection URL (Upstash) |
| `CORS_ORIGINS` | Cloud Run | Comma-separated frontend origins |
| `ENVIRONMENT` | Cloud Run | Set to `production` |
| `OPENAI_API_KEY` | Cloud Run | OpenAI API key for question generation |
| `RATE_LIMIT_ENABLED` | Cloud Run | Set to `true` in production |
| `GOOGLE_CLIENT_ID` | Cloud Run | Google OAuth (optional) |
| `FACEBOOK_CLIENT_ID` | Cloud Run | Facebook OAuth (optional) |
| `MICROSOFT_CLIENT_ID` | Cloud Run | Microsoft OAuth (optional) |
