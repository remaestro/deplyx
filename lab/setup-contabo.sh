#!/usr/bin/env bash
# ==============================================================================
# Deplyx Lab — Setup script for Contabo VPS
# ==============================================================================
#
# This script installs everything needed to run the deplyx lab on a fresh
# Contabo VPS (Ubuntu 22.04/24.04). Run as root or with sudo.
#
# Usage:
#   chmod +x setup-contabo.sh
#   sudo ./setup-contabo.sh
#
# After setup:
#   cd /opt/deplyx/lab
#   docker compose up -d
#
# ==============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
info() { echo -e "${BLUE}[i]${NC} $1"; }

echo ""
echo "============================================="
echo "  Deplyx Lab — Contabo VPS Setup"
echo "============================================="
echo ""

# 1. System update
info "Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq
log "System updated"

# 2. Install Docker
if command -v docker &>/dev/null; then
    log "Docker already installed: $(docker --version)"
else
    info "Installing Docker..."
    apt-get install -y -qq ca-certificates curl gnupg lsb-release

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    log "Docker installed: $(docker --version)"
fi

# 3. Install Docker Compose plugin (if not already)
if docker compose version &>/dev/null; then
    log "Docker Compose available: $(docker compose version)"
else
    err "Docker Compose plugin not found. Please install manually."
fi

# 4. Install useful tools
info "Installing utilities..."
apt-get install -y -qq git curl wget htop net-tools jq tree
log "Utilities installed"

# 5. Configure firewall
info "Configuring firewall..."
if command -v ufw &>/dev/null; then
    ufw allow 22/tcp     # SSH
    ufw allow 8001/tcp   # Deplyx backend (lab)
    ufw allow 5174/tcp   # Deplyx frontend (lab)
    ufw allow 7475/tcp   # Neo4j browser (lab)
    ufw --force enable
    log "Firewall configured (ports: 22, 8001, 5174, 7475)"
else
    warn "UFW not found, skipping firewall config"
fi

# 6. Clone or update deplyx
DEPLYX_DIR="/opt/deplyx"
if [ -d "$DEPLYX_DIR" ]; then
    info "Deplyx directory exists at $DEPLYX_DIR"
    cd "$DEPLYX_DIR"
    if [ -d ".git" ]; then
        git pull || warn "Git pull failed, using existing code"
    fi
else
    info "Cloning deplyx..."
    if [ -n "${DEPLYX_REPO:-}" ]; then
        git clone "$DEPLYX_REPO" "$DEPLYX_DIR"
    else
        warn "No DEPLYX_REPO env var set. Copy your code to $DEPLYX_DIR manually."
        mkdir -p "$DEPLYX_DIR/lab"
    fi
fi

# 7. System tuning for containers
info "Tuning system for containers..."
cat > /etc/sysctl.d/90-deplyx-lab.conf <<'EOF'
# Allow more container networking
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1

# More file descriptors for many containers
fs.file-max = 262144
fs.inotify.max_user_watches = 524288
fs.inotify.max_user_instances = 512

# Network buffers
net.core.somaxconn = 1024
net.ipv4.tcp_max_syn_backlog = 1024
EOF
sysctl --system > /dev/null 2>&1 || true
log "System tuned for containers"

# 8. Create convenience scripts
info "Creating convenience scripts..."

cat > "$DEPLYX_DIR/lab/start.sh" <<'SCRIPT'
#!/usr/bin/env bash
# Start the full lab
set -euo pipefail
cd "$(dirname "$0")"
echo "Starting deplyx lab..."
docker compose up -d --build
echo ""
echo "Lab is starting up. Wait ~30 seconds, then:"
echo "  Backend:  http://$(hostname -I | awk '{print $1}'):8001"
echo "  Frontend: http://$(hostname -I | awk '{print $1}'):5174"
echo "  Neo4j:    http://$(hostname -I | awk '{print $1}'):7475"
echo ""
echo "Mock devices:"
echo "  FW-DC1-01  (Fortinet):   10.100.0.10:443"
echo "  PA-DC1-01  (PaloAlto):   10.100.0.11:443"
echo "  CP-MGMT-01 (CheckPoint): 10.100.0.12:443"
echo "  SW-DC1-CORE (Cisco):     10.100.0.20:22"
echo "  SW-DC2-CORE (Juniper):   10.100.0.21:22"
SCRIPT
chmod +x "$DEPLYX_DIR/lab/start.sh"

cat > "$DEPLYX_DIR/lab/stop.sh" <<'SCRIPT'
#!/usr/bin/env bash
# Stop the lab
set -euo pipefail
cd "$(dirname "$0")"
echo "Stopping deplyx lab..."
docker compose down
echo "Lab stopped."
SCRIPT
chmod +x "$DEPLYX_DIR/lab/stop.sh"

cat > "$DEPLYX_DIR/lab/status.sh" <<'SCRIPT'
#!/usr/bin/env bash
# Show status of all lab services
set -euo pipefail
cd "$(dirname "$0")"
echo "=== Lab Status ==="
echo ""
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "=== Network Reachability ==="
for ip in 10.100.0.10 10.100.0.11 10.100.0.12 10.100.0.20 10.100.0.21; do
    name=$(docker ps --filter "network=lab_lab-net" --format '{{.Names}} {{.ID}}' 2>/dev/null | head -5)
    if docker exec deplyx-lab-backend timeout 2 bash -c "echo > /dev/tcp/$ip/443 || echo > /dev/tcp/$ip/22" 2>/dev/null; then
        echo "  ✓ $ip reachable"
    else
        echo "  ✗ $ip unreachable"
    fi
done
SCRIPT
chmod +x "$DEPLYX_DIR/lab/status.sh"

cat > "$DEPLYX_DIR/lab/test-connectors.sh" <<'SCRIPT'
#!/usr/bin/env bash
# Test connectivity to all mock devices from the backend container
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Testing Mock Device Connectivity ==="
echo ""

# Test Fortinet (HTTPS API)
echo -n "Fortinet FW-DC1-01 (10.100.0.10:443)... "
STATUS=$(docker exec deplyx-lab-backend python -c "
import requests, urllib3
urllib3.disable_warnings()
r = requests.get('https://10.100.0.10/api/v2/monitor/system/status',
    headers={'Authorization': 'Bearer fg-lab-token-001'}, verify=False, timeout=5)
print(r.json()['results']['hostname'])
" 2>&1) && echo "✓ $STATUS" || echo "✗ $STATUS"

# Test PaloAlto (HTTPS API)
echo -n "PaloAlto PA-DC1-01 (10.100.0.11:443)... "
STATUS=$(docker exec deplyx-lab-backend python -c "
import requests, urllib3
urllib3.disable_warnings()
r = requests.get('https://10.100.0.11/api/?type=op&cmd=<show><system><info></info></system></show>&key=pa-lab-apikey-001',
    verify=False, timeout=5)
print('OK' if '<hostname>' in r.text else 'FAIL')
" 2>&1) && echo "✓ $STATUS" || echo "✗ $STATUS"

# Test CheckPoint (HTTPS Web API)
echo -n "CheckPoint CP-MGMT-01 (10.100.0.12:443)... "
STATUS=$(docker exec deplyx-lab-backend python -c "
import requests, urllib3
urllib3.disable_warnings()
r = requests.post('https://10.100.0.12/web_api/login',
    json={'user': 'admin', 'password': 'Cp@ssw0rd!'}, verify=False, timeout=5)
sid = r.json().get('sid', '')
print('OK' if sid else 'FAIL')
" 2>&1) && echo "✓ $STATUS" || echo "✗ $STATUS"

# Test Cisco (SSH)
echo -n "Cisco SW-DC1-CORE (10.100.0.20:22)... "
STATUS=$(docker exec deplyx-lab-backend python -c "
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('10.100.0.20', username='admin', password='Cisco123!', timeout=5)
stdin, stdout, stderr = ssh.exec_command('show version')
out = stdout.read().decode()
ssh.close()
print('OK' if 'SW-DC1-CORE' in out else 'FAIL')
" 2>&1) && echo "✓ $STATUS" || echo "✗ $STATUS"

# Test Juniper (SSH)
echo -n "Juniper SW-DC2-CORE (10.100.0.21:22)... "
STATUS=$(docker exec deplyx-lab-backend python -c "
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('10.100.0.21', username='admin', password='Juniper123!', timeout=5)
stdin, stdout, stderr = ssh.exec_command('show version')
out = stdout.read().decode()
ssh.close()
print('OK' if 'SW-DC2-CORE' in out else 'FAIL')
" 2>&1) && echo "✓ $STATUS" || echo "✗ $STATUS"

echo ""
echo "Done."
SCRIPT
chmod +x "$DEPLYX_DIR/lab/test-connectors.sh"

log "Convenience scripts created"

# 9. Final summary
echo ""
echo "============================================="
echo "  Setup Complete!"
echo "============================================="
echo ""
echo "  Next steps:"
echo ""
echo "  1. Copy your deplyx code to $DEPLYX_DIR (if not cloned)"
echo ""
echo "  2. Start the lab:"
echo "     cd $DEPLYX_DIR/lab"
echo "     ./start.sh"
echo ""
echo "  3. Test device connectivity:"
echo "     ./test-connectors.sh"
echo ""
echo "  4. Register connectors in deplyx UI:"
echo "     http://<YOUR-VPS-IP>:5174"
echo ""
echo "  Resources used by the lab:"
echo "     ~2 GB RAM (all containers)"
echo "     ~3 GB disk (images + data)"
echo ""
echo "============================================="
