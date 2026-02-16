# Déploiement GCP (Cloud Run)

## Cible recommandée

- Backend: Cloud Run
- Frontend: Cloud Run (Nginx statique)
- Worker Celery: Cloud Run (service dédié)
- Postgres: Cloud SQL
- Redis: Memorystore
- Neo4j: AuraDB (recommandé sur GCP)

## 1) Pré-requis

- `gcloud` installé et authentifié
- Projet GCP actif
- API activées: Run, Artifact Registry, Secret Manager, Cloud SQL, Memorystore

## 2) Secrets

Créer au minimum:

- `JWT_SECRET_KEY`
- `NEO4J_PASSWORD`
- `POSTGRES_PASSWORD`

Exemple:

```bash
echo -n 'super-secret' | gcloud secrets create JWT_SECRET_KEY --data-file=-
```

Si le secret existe déjà, ajouter une version:

```bash
echo -n 'super-secret-v2' | gcloud secrets versions add JWT_SECRET_KEY --data-file=-
```

## 3) Variables d'env

Copier et adapter:

```bash
cp deploy/gcloud/env.backend.yaml.example deploy/gcloud/env.backend.yaml
```

## 4) Build & Deploy

Le script attend:

- `PROJECT_ID`
- `REGION` (ex: `europe-west1`)
- `FRONTEND_API_URL` (URL backend + `/api/v1`)

Optionnels (noms de secrets):

- `JWT_SECRET_NAME` (default: `JWT_SECRET_KEY`)
- `NEO4J_PASSWORD_SECRET_NAME` (default: `NEO4J_PASSWORD`)
- `POSTGRES_PASSWORD_SECRET_NAME` (default: `POSTGRES_PASSWORD`)

Exemple:

```bash
PROJECT_ID=my-gcp-project \
REGION=europe-west1 \
IMAGE_REPO=deplyx \
FRONTEND_API_URL=https://deplyx-backend-xxxxx.a.run.app/api/v1 \
bash deploy/gcloud/deploy.sh
```

## 5) Important

- Le worker Celery en Cloud Run nécessite Redis accessible depuis Cloud Run (VPC connector selon ton setup).
- Si tu veux un worker plus classique et stable, utilise GKE ou GCE pour le process Celery.
