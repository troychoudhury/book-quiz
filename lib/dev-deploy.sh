#!/usr/bin/env bash
#==============================================================================
# dev-deploy.sh — `dev deploy [all|backend|frontend] [--staging]`
#==============================================================================
# Deploys production images to Cloud Run (backend) and Firebase Hosting
# (frontend). Uses the pre-built image workflow: build → push → deploy so
# the exact same image is testable locally before it reaches production.
#
#   dev deploy backend            Deploy backend to Cloud Run
#   dev deploy frontend           Deploy frontend to Firebase Hosting
#   dev deploy all                Deploy both (default)
#   dev deploy --staging backend  Deploy to staging service instead of prod
#==============================================================================

DEPLOY_ENV="production"
DEPLOY_IMAGE=""  # set by build_and_push_image; consumed by backend/worker deploy

# ── shared build / env helpers ─────────────────────────────────────
# Build the backend image once and set $DEPLOY_IMAGE. Used by both the web
# service and the worker (same image, different command). Uses a global
# instead of echo-capture because docker's build/push progress goes to
# stdout and would corrupt a $(...) substitution.
build_and_push_image() {
    require_deploy_deps
    require_env_file

    local project image_tag
    project="$(gcloud config get-value project 2>/dev/null)" || {
        err "gcloud project not set. Run: gcloud config set project <project-id>"
        exit 1
    }
    image_tag="gcr.io/${project}/book-quiz-api:$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d-%H%M%S)"
    DEPLOY_IMAGE="${image_tag}"

    step "Building backend image (Dockerfile.cloudrun) → ${image_tag}"
    docker buildx build --load -f "${DEV_ROOT}/Dockerfile.cloudrun" -t "${image_tag}" "${DEV_ROOT}" || {
        err "Docker build failed."
        exit 1
    }

    step "Pushing image → ${image_tag}"
    docker push "${image_tag}" || {
        err "Docker push failed. Check gcloud auth: gcloud auth configure-docker"
        exit 1
    }
}

# Build an env-vars YAML file from .env.production (or .env if missing).
# --env-vars-file is used instead of --set-env-vars because the latter
# splits on commas and CORS_ORIGINS values contain commas — YAML handles
# commas and special characters without escaping issues.
# Prints the temp file path; the caller must rm it.
build_env_yaml() {
    local env_file="${DEV_ROOT}/.env.production"
    [[ ! -f "$env_file" ]] && env_file="${DEV_ROOT}/.env"
    local env_yaml
    env_yaml="$(mktemp)"
    python3 -c "
import sys, json
out = []
for line in open('$env_file'):
    line = line.strip()
    if not line or line.startswith('#') or line.startswith(('POSTGRES_DB=', 'POSTGRES_USER=', 'POSTGRES_PORT=', 'BACKEND_PORT=', 'FRONTEND_PORT=', 'DEBUG=')):
        continue
    key, _, val = line.partition('=')
    out.append(f'\"{key}\": {json.dumps(val)}')
print('\\n'.join(out))
" > "$env_yaml"
    echo "$env_yaml"
}

# Cloud SQL connection name from DATABASE_URL (empty when not used).
cloudsql_instance() {
    local env_file="${DEV_ROOT}/.env.production"
    [[ ! -f "$env_file" ]] && env_file="${DEV_ROOT}/.env"
    local db_url
    db_url="$(grep '^DATABASE_URL=' "$env_file" | cut -d= -f2-)"
    if echo "$db_url" | grep -q 'host=/cloudsql/'; then
        echo "$db_url" | grep -oP 'host=/cloudsql/\K[^?&]+' || true
    fi
}

# ── deploy backend (Cloud Run web service) ─────────────────────────
deploy_backend() {
    local image service_name env_yaml cloudsql_inst
    if [[ -z "$DEPLOY_IMAGE" ]]; then
        build_and_push_image
    fi
    image="$DEPLOY_IMAGE"
    service_name="book-quiz-api"
    [[ "$DEPLOY_ENV" == "staging" ]] && service_name="book-quiz-api-staging"
    env_yaml="$(build_env_yaml)"
    cloudsql_inst="$(cloudsql_instance)"

    local extra_flags=""
    [[ -n "$cloudsql_inst" ]] && extra_flags="--add-cloudsql-instances=${cloudsql_inst}"

    step "Deploying to Cloud Run (${service_name})"
    gcloud run deploy "${service_name}" \
        --image "${image}" \
        --region us-central1 \
        --platform managed \
        --allow-unauthenticated \
        ${extra_flags} \
        --env-vars-file="${env_yaml}"
    rm -f "$env_yaml"

    local url
    url="$(gcloud run services describe "${service_name}" --region us-central1 --format='value(status.url)' 2>/dev/null || true)"
    if [[ -n "$url" ]]; then
        ok "Backend deployed → ${url}"
    else
        ok "Backend deployed."
    fi
}

# ── deploy frontend (Firebase Hosting) ──────────────────────────────
deploy_frontend() {
    require_deploy_deps

    # We need the backend URL for the frontend build
    local api_url="${VITE_API_URL:-}"
    if [[ -z "$api_url" ]]; then
        # Try to get it from the Cloud Run service
        local service_name="book-quiz-api"
        [[ "$DEPLOY_ENV" == "staging" ]] && service_name="book-quiz-api-staging"
        api_url="$(gcloud run services describe "${service_name}" --region us-central1 --format='value(status.url)' 2>/dev/null || true)"
        if [[ -z "$api_url" ]]; then
            warn "Could not determine API URL. Set VITE_API_URL in your environment."
            read -r -p "Enter the backend API URL (e.g. https://book-quiz-api-xxx-uc.a.run.app): " api_url
        fi
    fi

    step "Building frontend (VITE_API_URL=${api_url})"
    (cd "${DEV_ROOT}/frontend" && VITE_API_URL="${api_url}" npm run build) || {
        err "Frontend build failed."
        exit 1
    }

    step "Deploying to Firebase Hosting"
    if ! command_exists firebase; then
        if command_exists npx; then
            info "Using npx firebase..."
            (cd "${DEV_ROOT}" && npx firebase deploy --only hosting) || {
                err "Firebase deploy failed."
                exit 1
            }
        else
            err "firebase CLI not found. Install with: npm i -g firebase-tools"
            exit 1
        fi
    else
        (cd "${DEV_ROOT}" && firebase deploy --only hosting) || {
            err "Firebase deploy failed."
            exit 1
        }
    fi

    ok "Frontend deployed → https://book-quiz.web.app"
}

# ── dependencies ────────────────────────────────────────────────────
require_deploy_deps() {
    if ! command_exists gcloud; then
        err "gcloud CLI is required for deployment."
        echo "  Install: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
    if ! command_exists docker; then
        err "Docker is required for building deployment images."
        exit 1
    fi
}

# ── main entry point ────────────────────────────────────────────────
cmd_deploy() {
    local target="all"

    # Parse flags
    for arg in "$@"; do
        case "$arg" in
            --staging) DEPLOY_ENV="staging" ;;
            --help|-h)
                echo "Usage: ./dev deploy [all|backend|frontend] [--staging]"
                echo ""
                echo "Deploy production images: backend to Cloud Run, frontend to Firebase."
                echo ""
                echo "  dev deploy                Deploy all (default)"
                echo "  dev deploy backend        Deploy backend web service to Cloud Run"
                echo "  dev deploy frontend       Deploy frontend to Firebase Hosting"
                echo "  dev deploy --staging      Deploy to staging environment"
                return 0
                ;;
            backend|frontend|all) target="$arg" ;;
            *) err "Unknown flag: $arg"; echo "Usage: ./dev deploy [all|backend|frontend] [--staging]"; exit 1 ;;
        esac
    done

    load_env

    info "Deploy target: ${target} | Environment: ${DEPLOY_ENV}"

    case "$target" in
        all)
            # Build/push the image once; backend reuses it.
            build_and_push_image
            deploy_backend
            deploy_frontend
            ;;
        backend)
            build_and_push_image
            deploy_backend
            ;;
        frontend)
            deploy_frontend
            ;;
    esac

    ok "Deploy complete (${DEPLOY_ENV})."
}
