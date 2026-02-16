# Deplyx

Stack mise en place:

- Backend: FastAPI (Python 3.11+), Pydantic, JWT, Passlib, Neo4j driver, SQLAlchemy
- Async jobs: Celery + Redis
- Frontend: React 18 + Vite + TypeScript + TailwindCSS + React Query + Zustand + React Flow
- Databases: Neo4j + PostgreSQL
- Local dev: Docker Compose

## Structure

- backend/
- frontend/
- docker-compose.yml
- .env.example

## Démarrage local

1. Copier les variables d'environnement:

```bash
cp .env.example .env
```

2. Lancer la stack:

```bash
docker compose up --build
```

3. URLs:

- Frontend: http://localhost:5173
- API: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474

## Variables d'environnement backend

Variables importantes (voir `.env.example`):

- `CORS_ALLOWED_ORIGINS` (liste séparée par des virgules)
- `APPROVAL_TIMEOUT_HOURS`
- `JWT_SECRET_KEY` (obligatoire et non par défaut en production)

## Backend - Connecteurs

Les connecteurs sont dans `backend/app/connectors` avec l'interface commune:

- `sync()`
- `validate_change()`
- `simulate_change()`
- `apply_change()`

## Déploiement GCP

Le setup de déploiement est dans `deploy/gcloud`.

Quickstart:

```bash
cp deploy/gcloud/env.backend.yaml.example deploy/gcloud/env.backend.yaml
```

Puis:

```bash
PROJECT_ID=my-gcp-project \
REGION=europe-west1 \
IMAGE_REPO=deplyx \
FRONTEND_API_URL=https://deplyx-backend-xxxxx.a.run.app/api/v1 \
bash deploy/gcloud/deploy.sh
```

Voir les détails dans `deploy/gcloud/README.md`.
