#!/usr/bin/env bash
set -euo pipefail

# Usage:
# PROJECT_ID=your-project REGION=europe-west1 \
# SERVICE_BACKEND=deplyx-backend SERVICE_FRONTEND=deplyx-frontend SERVICE_WORKER=deplyx-worker \
# IMAGE_REPO=deplyx FRONTEND_API_URL=https://deplyx-backend-xxxxx.a.run.app/api/v1 \
# ./deploy/gcloud/deploy.sh

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"
: "${SERVICE_BACKEND:=deplyx-backend}"
: "${SERVICE_FRONTEND:=deplyx-frontend}"
: "${SERVICE_WORKER:=deplyx-worker}"
: "${IMAGE_REPO:=deplyx}"
: "${FRONTEND_API_URL:?FRONTEND_API_URL is required (Cloud Run backend /api/v1 URL)}"
: "${JWT_SECRET_NAME:=JWT_SECRET_KEY}"
: "${NEO4J_PASSWORD_SECRET_NAME:=NEO4J_PASSWORD}"
: "${POSTGRES_PASSWORD_SECRET_NAME:=POSTGRES_PASSWORD}"

BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${IMAGE_REPO}/backend:$(date +%Y%m%d%H%M%S)"
FRONTEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${IMAGE_REPO}/frontend:$(date +%Y%m%d%H%M%S)"

echo "[1/8] Enable required services"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  --project "${PROJECT_ID}"

echo "[2/8] Configure project"
gcloud config set project "${PROJECT_ID}"

echo "[3/8] Ensure Artifact Registry exists"
gcloud artifacts repositories create "${IMAGE_REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project "${PROJECT_ID}" \
  || true

echo "[4/8] Build backend image"
gcloud builds submit . \
  --project "${PROJECT_ID}" \
  --config deploy/gcloud/cloudbuild.backend.yaml \
  --substitutions=_BACKEND_IMAGE="${BACKEND_IMAGE}"

echo "[5/8] Build frontend image"
gcloud builds submit . \
  --project "${PROJECT_ID}" \
  --config deploy/gcloud/cloudbuild.frontend.yaml \
  --substitutions=_FRONTEND_IMAGE="${FRONTEND_IMAGE}",_VITE_API_URL="${FRONTEND_API_URL}"

echo "[6/8] Deploy backend Cloud Run"
gcloud run deploy "${SERVICE_BACKEND}" \
  --image "${BACKEND_IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --set-secrets "JWT_SECRET_KEY=${JWT_SECRET_NAME}:latest,NEO4J_PASSWORD=${NEO4J_PASSWORD_SECRET_NAME}:latest,POSTGRES_PASSWORD=${POSTGRES_PASSWORD_SECRET_NAME}:latest" \
  --env-vars-file deploy/gcloud/env.backend.yaml

echo "[7/8] Deploy worker Cloud Run (Celery long-running)"
gcloud run deploy "${SERVICE_WORKER}" \
  --image "${BACKEND_IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --no-allow-unauthenticated \
  --command celery \
  --args "-A,app.worker.celery_app,worker,--loglevel=info" \
  --cpu 1 \
  --memory 512Mi \
  --min-instances 1 \
  --set-secrets "JWT_SECRET_KEY=${JWT_SECRET_NAME}:latest,NEO4J_PASSWORD=${NEO4J_PASSWORD_SECRET_NAME}:latest,POSTGRES_PASSWORD=${POSTGRES_PASSWORD_SECRET_NAME}:latest" \
  --env-vars-file deploy/gcloud/env.backend.yaml

echo "[8/8] Deploy frontend Cloud Run"
gcloud run deploy "${SERVICE_FRONTEND}" \
  --image "${FRONTEND_IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080

echo "Done. Fetch service URLs:"
gcloud run services describe "${SERVICE_BACKEND}" --region "${REGION}" --format='value(status.url)'
gcloud run services describe "${SERVICE_FRONTEND}" --region "${REGION}" --format='value(status.url)'
