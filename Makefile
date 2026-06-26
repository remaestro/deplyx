.PHONY: up down db backend frontend logs-backend logs-frontend

export NEO4J_URI ?= bolt://localhost:7688
export POSTGRES_HOST ?= localhost
export POSTGRES_PORT ?= 5452
export REDIS_URL ?= redis://localhost:6381/0
export BACKEND_PORT ?= 8100
export FRONTEND_PORT ?= 5173
export VENV ?= ../.venv

up: db backend frontend
	@echo "✓ All services: backend :$(BACKEND_PORT) | frontend :$(FRONTEND_PORT)"

db:
	@podman ps --filter name=deplyx-postgres | grep -q deplyx-postgres && echo "✓ Databases already up" || (podman-compose up -d postgres neo4j redis && sleep 5 && echo "✓ Databases up")

backend: db
	@lsof -i :$(BACKEND_PORT) >/dev/null 2>&1 && echo "✓ Backend already on :$(BACKEND_PORT)" || \
		(cd backend && \
		NEO4J_URI=$(NEO4J_URI) \
		POSTGRES_HOST=$(POSTGRES_HOST) \
		POSTGRES_PORT=$(POSTGRES_PORT) \
		REDIS_URL=$(REDIS_URL) \
		nohup ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $(BACKEND_PORT) --reload > /tmp/deplyx-backend.log 2>&1 & \
		sleep 3 && curl -s http://localhost:$(BACKEND_PORT)/health >/dev/null && echo "✓ Backend on :$(BACKEND_PORT)")

frontend: db
	@lsof -i :$(FRONTEND_PORT) >/dev/null 2>&1 && echo "✓ Frontend already on :$(FRONTEND_PORT)" || \
		(cd frontend && nohup npx vite dev --host 0.0.0.0 --port $(FRONTEND_PORT) --strictPort > /tmp/deplyx-frontend.log 2>&1 & \
		sleep 3 && echo "✓ Frontend on :$(FRONTEND_PORT)")

down:
	@-pkill -f "uvicorn app.main" 2>/dev/null && echo "✓ Backend stopped" || true
	@-pkill -f "vite" 2>/dev/null && echo "✓ Frontend stopped" || true

stop-db:
	@podman-compose down 2>/dev/null && echo "✓ Databases stopped" || true

logs-backend:
	@tail -f /tmp/deplyx-backend.log

logs-frontend:
	@tail -f /tmp/deplyx-frontend.log
