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
echo "▶ Running database setup…"

# First ensure all tables exist (create_all), then run or stamp alembic
python3 -c "
from sqlalchemy import create_engine, inspect, text
from app.core.config import settings
from app.models.base import Base
# Import all models so metadata is populated
from app.models import connector, user, change, policy, approval, audit_log

e = create_engine(settings.postgres_dsn_sync)
insp = inspect(e)
existing = insp.get_table_names()

if 'users' not in existing:
    print('  Creating all tables from scratch…')
    Base.metadata.create_all(e)
    print('  Tables created ✓')
else:
    print(f'  Tables already exist ({len(existing)} tables)')
"

# Now run alembic - if tables were just created, stamp head; otherwise upgrade
python3 -c "
from sqlalchemy import create_engine, text
from app.core.config import settings
e = create_engine(settings.postgres_dsn_sync)
with e.connect() as c:
    try:
        row = c.execute(text('SELECT version_num FROM alembic_version')).first()
        if row:
            print(f'  Alembic at {row[0]} — running upgrade head')
            import subprocess, sys
            r = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True)
            print(r.stdout)
            if r.returncode != 0:
                print(r.stderr)
                sys.exit(r.returncode)
        else:
            raise Exception('empty')
    except Exception:
        print('  Fresh DB — stamping alembic to head')
        import subprocess
        subprocess.run(['alembic', 'stamp', 'head'], check=True)
"
echo "  Database ready ✓"

# ── Start the app ────────────────────────────────────────────────────────
if [ $# -gt 0 ]; then
  echo "▶ Running custom command: $@"
  exec "$@"
else
  echo "▶ Starting uvicorn on port ${PORT:-8080}…"
  exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
fi
