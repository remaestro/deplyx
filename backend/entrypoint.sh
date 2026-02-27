#!/usr/bin/env bash
set -e

# ── Wait for Postgres ────────────────────────────────────────────────────
echo "▶ Waiting for Postgres…"
MAX_WAIT=30
for i in $(seq 1 $MAX_WAIT); do
  if python3 -c "
import sys, os
try:
    from app.core.config import settings
    from sqlalchemy import create_engine, text
    e = create_engine(settings.postgres_dsn_sync)
    with e.connect() as c:
        c.execute(text('SELECT 1'))
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
    echo "  Postgres ready ✓"
    break
  fi
  if [ "$i" -eq "$MAX_WAIT" ]; then
    echo "  ✗ Postgres not ready after ${MAX_WAIT}s — continuing anyway"
  fi
  sleep 1
done

# ── Alembic migrations ───────────────────────────────────────────────────
echo "▶ Running Alembic migrations…"

# If alembic_version table doesn't exist or has no rows, stamp current
# state so upgrade head can proceed from there
python3 -c "
from sqlalchemy import create_engine, text, inspect
from app.core.config import settings
e = create_engine(settings.postgres_dsn_sync)
with e.connect() as c:
    insp = inspect(e)
    if 'alembic_version' not in insp.get_table_names():
        print('  No alembic_version table — will stamp after create_all')
    else:
        row = c.execute(text('SELECT version_num FROM alembic_version')).first()
        if row:
            print(f'  Current DB revision: {row[0]}')
        else:
            print('  alembic_version empty — will stamp')
" 2>/dev/null || true

alembic upgrade head
echo "  Alembic migrations applied ✓"

# ── Start the app ────────────────────────────────────────────────────────
if [ $# -gt 0 ]; then
  echo "▶ Running custom command: $@"
  exec "$@"
else
  echo "▶ Starting uvicorn on port ${PORT:-8080}…"
  exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
fi
