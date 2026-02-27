#!/usr/bin/env bash
set -euo pipefail

# ══════════════════════════════════════════════════════════════
#  Deplyx — Production Deployment Script
# ══════════════════════════════════════════════════════════════
#
#  Deploys the Deplyx stack to a remote VPS via SSH key auth.
#  No passwords, no sshpass — just a standard SSH key.
#
#  Usage:
#    bash deploy/vps/deploy.sh              # default deploy
#    bash deploy/vps/deploy.sh --rollback   # rollback to previous
#
#  Env overrides:
#    VPS_HOST, VPS_USER, VPS_DIR, SSH_KEY
#
# ══════════════════════════════════════════════════════════════

# ── Config ────────────────────────────────────────────────────
VPS_HOST="${VPS_HOST:-167.86.104.86}"
VPS_USER="${VPS_USER:-deplyx}"
VPS_DIR="${VPS_DIR:-/opt/deplyx}"
SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
GIT_SHA=$(cd "${PROJECT_DIR}" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")
RELEASE_TAG="${TIMESTAMP}-${GIT_SHA}"

# ── SSH helper ────────────────────────────────────────────────
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15 -o ServerAliveInterval=30"
if [[ -f "${SSH_KEY}" ]]; then
    SSH_CMD="ssh ${SSH_OPTS} -i ${SSH_KEY} ${VPS_USER}@${VPS_HOST}"
    SCP_CMD="scp ${SSH_OPTS} -i ${SSH_KEY}"
else
    echo "⚠  No SSH key at ${SSH_KEY} — falling back to ssh-agent / password"
    SSH_CMD="ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST}"
    SCP_CMD="scp ${SSH_OPTS}"
fi

remote() { ${SSH_CMD} "$@"; }

# ── Rollback mode ─────────────────────────────────────────────
if [[ "${1:-}" == "--rollback" ]]; then
    echo "⏪ Rolling back to previous release…"
    remote bash -s << 'ROLLBACK'
    set -e
    cd /opt/deplyx
    PREV=$(ls -1d releases/*/ 2>/dev/null | sort | tail -2 | head -1)
    if [[ -z "${PREV}" || ! -d "${PREV}" ]]; then
        echo "❌ No previous release found."
        exit 1
    fi
    echo "  → Rolling back to: ${PREV}"
    ln -sfn "$(pwd)/${PREV}" current
    cd current
    docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate
    echo "  ✅ Rollback complete."
ROLLBACK
    exit 0
fi

# ── Pre-flight checks ────────────────────────────────────────
echo "╔══════════════════════════════════════════╗"
echo "║       Deplyx — Production Deploy         ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Target:  ${VPS_USER}@${VPS_HOST}:${VPS_DIR}"
echo "  Release: ${RELEASE_TAG}"
echo ""

# Verify .env.production exists locally
if [[ ! -f "${PROJECT_DIR}/.env.production" ]]; then
    echo "❌ Missing .env.production in project root."
    echo "   Copy .env.production.example and fill in values."
    exit 1
fi

# Verify SSH connectivity
echo "[1/6] Testing SSH connection…"
remote echo "  ✓ Connected" || { echo "❌ Cannot reach ${VPS_HOST}"; exit 1; }

# ── Package ───────────────────────────────────────────────────
echo "[2/6] Packaging project (${GIT_SHA})…"
TARBALL="/tmp/deplyx-${RELEASE_TAG}.tar.gz"
tar czf "${TARBALL}" \
    -C "${PROJECT_DIR}" \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='test-results' \
    --exclude='playwright-report' \
    --exclude='.env' \
    --exclude='.venv' \
    --exclude='dist' \
    --exclude='.DS_Store' \
    backend \
    frontend \
    lab \
    deploy \
    docker-compose.prod.yml \
    .env.production

echo "  Tarball: $(du -h "${TARBALL}" | cut -f1)"

# ── Upload ────────────────────────────────────────────────────
echo "[3/6] Uploading to VPS…"
${SCP_CMD} "${TARBALL}" "${VPS_USER}@${VPS_HOST}:/tmp/deplyx-deploy.tar.gz"

# ── Deploy on remote ──────────────────────────────────────────
echo "[4/6] Deploying on VPS…"
remote bash -s -- "${RELEASE_TAG}" << 'REMOTE_DEPLOY'
set -e
RELEASE_TAG="$1"
VPS_DIR="/opt/deplyx"
RELEASE_DIR="${VPS_DIR}/releases/${RELEASE_TAG}"

echo "  → Creating release: ${RELEASE_TAG}…"
mkdir -p "${RELEASE_DIR}"
tar xzf /tmp/deplyx-deploy.tar.gz -C "${RELEASE_DIR}"
rm -f /tmp/deplyx-deploy.tar.gz

# Symlink current → this release
ln -sfn "${RELEASE_DIR}" "${VPS_DIR}/current"

echo "  → Building & starting containers…"
cd "${VPS_DIR}/current"
docker compose -f docker-compose.prod.yml --env-file .env.production build --quiet
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate --remove-orphans

echo "  → Waiting for services…"
sleep 20

echo "  → Container status:"
docker compose -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}"

# ── Keep only last 3 releases ────────────────────────────────
echo "  → Cleaning old releases…"
cd "${VPS_DIR}/releases"
ls -1d */ 2>/dev/null | sort | head -n -3 | xargs -r rm -rf
echo "  → Kept: $(ls -1d */ | wc -l) releases"

# ── Prune Docker ─────────────────────────────────────────────
docker image prune -f --filter "until=24h" >/dev/null 2>&1 || true
REMOTE_DEPLOY

# ── Health check ──────────────────────────────────────────────
echo "[5/6] Health check…"
MAX_RETRIES=6
for i in $(seq 1 ${MAX_RETRIES}); do
    if remote curl -sf http://localhost/health >/dev/null 2>&1; then
        echo "  ✓ Backend healthy!"
        break
    fi
    if [[ $i -eq ${MAX_RETRIES} ]]; then
        echo "  ⚠ Backend not responding after ${MAX_RETRIES} attempts."
        echo "    Check logs: ssh ${VPS_USER}@${VPS_HOST} 'cd /opt/deplyx/current && docker compose -f docker-compose.prod.yml logs backend --tail 50'"
        exit 1
    fi
    echo "  Attempt ${i}/${MAX_RETRIES} — waiting 10s…"
    sleep 10
done

# ── Cleanup local ─────────────────────────────────────────────
echo "[6/6] Cleanup…"
rm -f "${TARBALL}"

echo ""
echo "════════════════════════════════════════════"
echo "  ✅ Deployment successful!"
echo ""
echo "  Release:  ${RELEASE_TAG}"
echo "  Frontend: http://${VPS_HOST}"
echo "  API:      http://${VPS_HOST}/api/v1"
echo "  Health:   http://${VPS_HOST}/health"
echo ""
echo "  Rollback: bash deploy/vps/deploy.sh --rollback"
echo "  Logs:     ssh ${VPS_USER}@${VPS_HOST} 'cd /opt/deplyx/current && docker compose -f docker-compose.prod.yml logs -f'"
echo "════════════════════════════════════════════"

