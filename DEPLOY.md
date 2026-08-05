# Deploying Book Quiz to Google Firebase + Cloud Run

## Architecture

```
┌─────────────────────┐     ┌──────────────────┐     ┌────────────────┐
│  Firebase Hosting   │────▶│   Cloud Run       │────▶│   Cloud SQL     │
│  (React SPA)        │     │   (FastAPI)        │     │   (PostgreSQL)   │
│  book-quiz.web.app  │     │   api-xxxx.run.app │     │                  │
└─────────────────────┘     └──────────────────┘     └────────────────┘
```

## Prerequisites

1. Google Cloud project with billing enabled (Blaze plan)
2. Firebase CLI: `npm i -g firebase-tools`
3. Google Cloud CLI: `gcloud` installed and authenticated
4. Domain verification (optional, for custom domain)

## 1. Database — Cloud SQL

```bash
# Create PostgreSQL instance (smallest for dev: db-f1-micro ~$9/mo)
gcloud sql instances create book-quiz-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=us-central1

# Create database
gcloud sql databases create bookquiz --instance=book-quiz-db

# Create user
gcloud sql users create bookquiz \
  --instance=book-quiz-db \
  --password=<your-password>

# Get connection name (needed for Cloud Run)
gcloud sql instances describe book-quiz-db --format='value(connectionName)'
```

## 2. Backend — Cloud Run

```bash
# Build and deploy
gcloud run deploy book-quiz-api \
  --source . \
  --file=Dockerfile.cloudrun \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --add-cloudsql-instances=<connection-name> \
  --set-env-vars="
    DATABASE_URL=postgresql://bookquiz:<password>@/bookquiz?host=/cloudsql/<connection-name>,
    JWT_SECRET_KEY=<random-64-char-secret>,
    ADMIN_API_KEY=<random-secret>,
    REDIS_URL=redis://<redis-host>:6379/0,
    CORS_ORIGINS=https://book-quiz.web.app,
    ENVIRONMENT=production
  "

# After deploy, update frontend .env.production with the Cloud Run URL
```

## 3. Frontend — Firebase Hosting

```bash
# Install Firebase CLI
npm i -g firebase-tools

# Login to Firebase
firebase login

# Init hosting (already configured — skip if firebase.json exists)
firebase init hosting

# Build the frontend with production API URL
cd frontend
VITE_API_URL=<cloud-run-url> npm run build

# Deploy
firebase deploy --only hosting
```

## 4. Post-Deploy Verification

```bash
# Health check
curl https://<cloud-run-url>/api/v1/health

# Frontend
curl https://book-quiz.web.app

# Database connectivity
curl https://<cloud-run-url>/api/v1/books/autocomplete?q=harry
```

## Environment Variables Reference

| Variable | Where | Description |
|----------|-------|-------------|
| `VITE_API_URL` | Frontend build | Cloud Run service URL |
| `DATABASE_URL` | Cloud Run | Cloud SQL connection |
| `JWT_SECRET_KEY` | Cloud Run | 64-char random string |
| `ADMIN_API_KEY` | Cloud Run | Admin API key |
| `REDIS_URL` | Cloud Run | Redis (Cloud Memorystore or external) |
| `CORS_ORIGINS` | Cloud Run | Comma-separated frontend origins |
| `ENVIRONMENT` | Cloud Run | Set to `production` |
| `GOOGLE_CLIENT_ID` | Cloud Run | OAuth (optional) |
| `FACEBOOK_CLIENT_ID` | Cloud Run | OAuth (optional) |
| `MICROSOFT_CLIENT_ID` | Cloud Run | OAuth (optional) |

## Optional: SQL Connect

Firebase SQL Connect bridges Firebase services to Cloud SQL via a Data Connect service. This is separate from the FastAPI direct connection and useful if you want Firebase Functions/Extensions to query the database. For this app, FastAPI already connects directly to Cloud SQL — SQL Connect is optional.
