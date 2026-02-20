"""Mock Grafana SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("GRAFANA_HOSTNAME", "grafana-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Grafana123!")

COMMANDS = {
    "grafana-cli info": f"""Grafana CLI version 11.3.0

Installed plugins in /var/lib/grafana/plugins:
  alexanderzobnin-zabbix-app (4.4.5)
  grafana-piechart-panel (1.6.4)
  grafana-worldmap-panel (0.3.3)
  marcusolsson-json-datasource (1.3.2)
  
Grafana Server:
  Version: 11.3.0
  Commit: abc12345
  Platform: linux/amd64
{HOSTNAME}$ """,

    "grafana-cli datasources list": f"""Datasources configured in /etc/grafana/provisioning/datasources:
  1. Prometheus   (default) - http://prometheus:9090 - [UID: prometheus-main]
  2. Elasticsearch           - https://elastic-node-01:9200 - [UID: es-prod]
  3. PostgreSQL              - postgres-db-01:5432/analytics - [UID: pg-analytics]
  4. Loki                   - http://loki:3100 - [UID: loki-main]
{HOSTNAME}$ """,

    "curl localhost:3000/api/health": f"""{{
  "commit": "abc12345",
  "database": "ok",
  "version": "11.3.0"
}}
{HOSTNAME}$ """,

    "curl localhost:3000/api/dashboards/tags": f"""[
  {{"term":"infrastructure","count":12}},
  {{"term":"application","count":8}},
  {{"term":"security","count":5}},
  {{"term":"network","count":15}},
  {{"term":"kubernetes","count":22}}
]
{HOSTNAME}$ """,

    "curl localhost:3000/api/alert-notifications": f"""Total active alert rules: 47
  Firing:  3
  Pending: 1
  Normal: 43

Recent firings:
  [FIRING] High CPU on app-server-01 (cpu_usage > 90% for 5m)
  [FIRING] Disk space low on postgres-db-01 (disk_free < 10GB)
  [FIRING] Elasticsearch heap > 80% on elastic-node-01
{HOSTNAME}$ """,

    "systemctl status grafana-server": f"""● grafana-server.service - Grafana instance
     Loaded: loaded (/lib/systemd/system/grafana-server.service; enabled)
     Active: active (running) since Mon 2024-10-01 00:00:00 UTC; 83 days 14h ago
   Main PID: 5678 (grafana)
     Memory: 256.4M
{HOSTNAME}$ """,
}


class MockSSH(paramiko.ServerInterface):
    def check_channel_request(self, kind, chanid): return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
    def check_auth_password(self, username, password): return paramiko.AUTH_SUCCESSFUL if username == SSH_USER and password == SSH_PASS else paramiko.AUTH_FAILED
    def check_channel_shell_request(self, channel): return True
    def get_allowed_auths(self, username): return "password,publickey"
    def check_auth_publickey(self, username, key): return paramiko.AUTH_SUCCESSFUL


def handle_client(sock, addr):
    t = paramiko.Transport(sock)
    t.add_server_key(HOST_KEY)
    t.start_server(server=MockSSH())
    ch = t.accept(30)
    if not ch: t.close(); return
    try:
        ch.sendall(f"\r\n{HOSTNAME}$ ".encode())
        buf = b""
        while True:
            data = ch.recv(4096)
            if not data: break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                cmd = line.decode("utf-8", errors="ignore").strip().rstrip("\r")
                if not cmd: ch.sendall(f"\r\n{HOSTNAME}$ ".encode()); continue
                if cmd in ("exit", "quit"): return
                resp = next((v for k, v in COMMANDS.items() if cmd.lower().startswith(k.lower())), f"bash: command not found\r\n{HOSTNAME}$ ")
                ch.sendall(f"\r\n{resp}\r\n".encode())
    except Exception: pass
    finally:
        try: ch.close()
        except: pass
        t.close()


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", SSH_PORT)); s.listen(5)
    print(f"[Mock Grafana {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
