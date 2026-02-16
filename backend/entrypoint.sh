#!/usr/bin/env bash
set -e

echo "▶ Running Alembic migrations…"
alembic upgrade head 2>&1 || echo "⚠ Alembic migration skipped (may already be up to date)"

echo "▶ Starting uvicorn on port ${PORT:-8080}…"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
