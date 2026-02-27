#!/usr/bin/env bash
set -euo pipefail

# ══════════════════════════════════════════════════════════════
#  Deplyx — One-time VPS Setup Script
# ══════════════════════════════════════════════════════════════
#
#  Run this ONCE from your Mac to prepare a fresh VPS.
#
#  Prerequisites:
#    - SSH access to the VPS (key or password)
#    - Ubuntu 22.04+ on the VPS
#
#  Usage:
#    bash deploy/vps/setup-vps.sh
#
# ══════════════════════════════════════════════════════════════

VPS_HOST="${VPS_HOST:-167.86.104.86}"
VPS_USER="${VPS_USER:-root}"
SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"
DEPLOY_USER="deplyx"
VPS_DIR="/opt/deplyx"

# ── Detect SSH auth method ────────────────────────────────────
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15"
if [[ -f "${SSH_KEY}" ]]; then
    SSH_CMD="ssh ${SSH_OPTS} -i ${SSH_KEY} ${VPS_USER}@${VPS_HOST}"
    SCP_CMD="scp ${SSH_OPTS} -i ${SSH_KEY}"
else
    echo "⚠  No SSH key found at ${SSH_KEY}"
    echo "   Will use password auth (you'll be prompted)."
    SSH_CMD="ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST}"
    SCP_CMD="scp ${SSH_OPTS}"
fi

echo "╔══════════════════════════════════════════╗"
echo "║      Deplyx — VPS Initial Setup          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Target: ${VPS_USER}@${VPS_HOST}"
echo ""

# ── Copy SSH public key for deplyx user ───────────────────────
PUB_KEY=""
for key_file in "${SSH_KEY}.pub" "${HOME}/.ssh/id_ed25519.pub" "${HOME}/.ssh/id_rsa.pub"; do
    if [[ -f "${key_file}" ]]; then
        PUB_KEY=$(cat "${key_file}")
        echo "[✓] Found public key: ${key_file}"
        break
    fi
done

if [[ -z "${PUB_KEY}" ]]; then
    echo "[!] No SSH public key found. Generating one…"
    ssh-keygen -t ed25519 -C "deplyx-deploy" -f "${HOME}/.ssh/deplyx_vps" -N ""
    PUB_KEY=$(cat "${HOME}/.ssh/deplyx_vps.pub")
    SSH_KEY="${HOME}/.ssh/deplyx_vps"
    echo "[✓] Generated: ${HOME}/.ssh/deplyx_vps"
fi

# ── Run remote setup ──────────────────────────────────────────
echo ""
echo "[1/5] Running remote setup…"

${SSH_CMD} bash -s -- "${DEPLOY_USER}" "${VPS_DIR}" "${PUB_KEY}" << 'SETUP_SCRIPT'
set -euo pipefail
DEPLOY_USER="$1"
VPS_DIR="$2"
PUB_KEY="$3"

echo "  → Updating system packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

echo "  → Installing essentials…"
apt-get install -y -qq curl wget git ufw fail2ban unattended-upgrades apt-listchanges

# ── Create deploy user ────────────────────────────────────────
echo "  → Setting up user: ${DEPLOY_USER}…"
if ! id "${DEPLOY_USER}" &>/dev/null; then
    adduser --disabled-password --gecos "Deplyx Deploy" "${DEPLOY_USER}"
fi
usermod -aG docker "${DEPLOY_USER}" 2>/dev/null || true
usermod -aG sudo "${DEPLOY_USER}"
echo "${DEPLOY_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${DEPLOY_USER}"
chmod 440 "/etc/sudoers.d/${DEPLOY_USER}"

# ── SSH key for deploy user ───────────────────────────────────
echo "  → Installing SSH key for ${DEPLOY_USER}…"
USER_HOME="/home/${DEPLOY_USER}"
mkdir -p "${USER_HOME}/.ssh"
echo "${PUB_KEY}" > "${USER_HOME}/.ssh/authorized_keys"
chmod 700 "${USER_HOME}/.ssh"
chmod 600 "${USER_HOME}/.ssh/authorized_keys"
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${USER_HOME}/.ssh"

# ── Harden SSH ────────────────────────────────────────────────
echo "  → Hardening SSH…"
SSHD_CONF="/etc/ssh/sshd_config"
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' "${SSHD_CONF}"
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' "${SSHD_CONF}"
sed -i 's/^#\?PubkeyAuthentication .*/PubkeyAuthentication yes/' "${SSHD_CONF}"
systemctl restart sshd

# ── Firewall ──────────────────────────────────────────────────
echo "  → Configuring firewall…"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
ufw allow 80/tcp comment "HTTP"
ufw allow 443/tcp comment "HTTPS"
echo "y" | ufw enable

# ── Swap (if not already configured) ─────────────────────────
if ! swapon --show | grep -q "/swapfile"; then
    echo "  → Creating 4G swap…"
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q "/swapfile" /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
else
    echo "  → Swap already configured."
fi

# ── Docker (if not installed) ─────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "  → Installing Docker…"
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    usermod -aG docker "${DEPLOY_USER}"
fi

# ── Create deploy directory ───────────────────────────────────
echo "  → Creating ${VPS_DIR}…"
mkdir -p "${VPS_DIR}"
chown "${DEPLOY_USER}:${DEPLOY_USER}" "${VPS_DIR}"

# ── Unattended security upgrades ──────────────────────────────
echo "  → Enabling automatic security updates…"
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'APT_CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT_CONF

# ── Docker log rotation ──────────────────────────────────────
echo "  → Configuring Docker log rotation…"
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'DOCKER_CONF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
DOCKER_CONF
systemctl restart docker

echo ""
echo "  ✅ VPS setup complete!"
SETUP_SCRIPT

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         VPS Setup Complete!              ║"
echo "╠══════════════════════════════════════════╣"
echo "║                                          ║"
echo "║  SSH:  ssh deplyx@${VPS_HOST}            ║"
echo "║  Dir:  /opt/deplyx                       ║"
echo "║                                          ║"
echo "║  Root login:  DISABLED                   ║"
echo "║  Password:    DISABLED                   ║"
echo "║  Firewall:    22, 80, 443 only           ║"
echo "║  Swap:        4 GB                       ║"
echo "║                                          ║"
echo "║  Next: bash deploy/vps/deploy.sh         ║"
echo "╚══════════════════════════════════════════╝"
