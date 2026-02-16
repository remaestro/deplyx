#!/usr/bin/env bash
set -euo pipefail

# ── Deplyx VPS Deploy Script ──────────────────────────────────
# Usage: bash deploy/vps/deploy.sh
# Uses sshpass for non-interactive deployment.

VPS_HOST="${VPS_HOST:-167.86.104.86}"
VPS_USER="${VPS_USER:-root}"
VPS_PASS="${VPS_PASS:-rootroot}"
VPS_DIR="${VPS_DIR:-/opt/deplyx}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

echo "╔══════════════════════════════════════════╗"
echo "║         Deplyx VPS Deployment            ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Target: ${VPS_USER}@${VPS_HOST}:${VPS_DIR}"
echo ""

# ── Step 1: Create tarball locally ────────────────────────────
echo "[1/4] Packaging project…"
TARBALL="/tmp/deplyx-deploy.tar.gz"
tar czf "${TARBALL}" \
  -C "${PROJECT_DIR}" \
  --exclude='node_modules' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='test-results' \
  --exclude='.env' \
  --exclude='.venv' \
  --exclude='dist' \
  backend \
  frontend \
  deploy \
  docker-compose.prod.yml \
  .env.production

echo "    Tarball: $(du -h "${TARBALL}" | cut -f1)"

# ── Step 2: Upload tarball ────────────────────────────────────
echo "[2/4] Uploading to VPS…"
sshpass -p "${VPS_PASS}" scp ${SSH_OPTS} "${TARBALL}" "${VPS_USER}@${VPS_HOST}:/tmp/deplyx-deploy.tar.gz"

# ── Step 3: SSH & deploy everything ───────────────────────────
echo "[3/4] Building & starting on VPS…"
sshpass -p "${VPS_PASS}" ssh ${SSH_OPTS} "${VPS_USER}@${VPS_HOST}" << 'REMOTE_SCRIPT'
set -e

VPS_DIR="/opt/deplyx"

echo "  → Extracting files…"
mkdir -p "${VPS_DIR}"
tar xzf /tmp/deplyx-deploy.tar.gz -C "${VPS_DIR}"
rm -f /tmp/deplyx-deploy.tar.gz

echo "  → Stopping old containers…"
cd "${VPS_DIR}"
docker compose -f docker-compose.prod.yml --env-file .env.production down --remove-orphans 2>/dev/null || true

echo "  → Building images (this may take a few minutes on first run)…"
docker compose -f docker-compose.prod.yml --env-file .env.production build

echo "  → Starting containers…"
docker compose -f docker-compose.prod.yml --env-file .env.production up -d

echo "  → Waiting 15s for services to start…"
sleep 15

echo "  → Container status:"
docker compose -f docker-compose.prod.yml ps

echo "  → Checking health…"
curl -sf http://localhost/health 2>/dev/null && echo " ✓ Backend healthy" || echo " ⚠ Backend not yet ready (may need a minute)"

echo "  → Cleaning up old images…"
docker image prune -f 2>/dev/null || true
REMOTE_SCRIPT

# ── Step 4: Done ──────────────────────────────────────────────
rm -f "${TARBALL}"

echo ""
echo "════════════════════════════════════════════"
echo "  ✓ Deployment complete!"
echo ""
echo "  Frontend: http://${VPS_HOST}"
echo "  API:      http://${VPS_HOST}/api/v1"
echo "  Health:   http://${VPS_HOST}/health"
echo "════════════════════════════════════════════"

