"""Mock Prometheus SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("PROM_HOSTNAME", "prometheus-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Prom123!")

COMMANDS = {
    "promtool check config /etc/prometheus/prometheus.yml": f"""Checking /etc/prometheus/prometheus.yml
  SUCCESS: /etc/prometheus/prometheus.yml is valid prometheus config file syntax
  Found alertmanagerconfig file /etc/prometheus/alertmanager.yml
  Found 3 alert rule files
{HOSTNAME}$ """,

    "curl localhost:9090/api/v1/targets": f"""{{
  "status": "success",
  "data": {{
    "activeTargets": [
      {{ "labels": {{ "job": "node", "instance": "app-server-01:9100" }}, "health": "up", "lastScrape": "2024-12-01T14:22:28.000Z" }},
      {{ "labels": {{ "job": "node", "instance": "app-server-02:9100" }}, "health": "up", "lastScrape": "2024-12-01T14:22:29.000Z" }},
      {{ "labels": {{ "job": "node", "instance": "db-server-01:9100" }},  "health": "up", "lastScrape": "2024-12-01T14:22:31.000Z" }},
      {{ "labels": {{ "job": "postgres", "instance": "postgres-db-01:9187" }}, "health": "up",  "lastScrape": "2024-12-01T14:22:30.000Z" }},
      {{ "labels": {{ "job": "nginx", "instance": "nginx-web-01:9113" }},    "health": "up",  "lastScrape": "2024-12-01T14:22:27.000Z" }},
      {{ "labels": {{ "job": "redis", "instance": "redis-cache-01:9121" }},  "health": "up",  "lastScrape": "2024-12-01T14:22:32.000Z" }},
      {{ "labels": {{ "job": "elasticsearch", "instance": "elastic-node-01:9114" }}, "health": "up", "lastScrape": "2024-12-01T14:22:22.000Z" }},
      {{ "labels": {{ "job": "snmp", "instance": "fortinet-fw-01:161" }},   "health": "up",  "lastScrape": "2024-12-01T14:22:20.000Z" }},
      {{ "labels": {{ "job": "blackbox", "instance": "https://corp.local" }}, "health": "up", "lastScrape": "2024-12-01T14:22:18.000Z" }}
    ],
    "droppedTargets": []
  }}
}}
{HOSTNAME}$ """,

    "curl localhost:9090/api/v1/alertmanagers": f"""{{
  "status": "success",
  "data": {{
    "activeAlertmanagers": [
      {{ "url": "http://alertmanager:9093/api/v2/alerts" }}
    ],
    "droppedAlertmanagers": []
  }}
}}
{HOSTNAME}$ """,

    "curl localhost:9090/api/v1/rules": f"""Active alert rules: 47 total (3 firing)
  groups:
    - node-alerts (15 rules): cpu_high, mem_high, disk_low, ...
    - app-alerts (12 rules): response_time_high, error_rate, ...
    - infra-alerts (10 rules): pod_restart, pvc_full, ...
    - security-alerts (10 rules): failed_logins, port_scan, ...
{HOSTNAME}$ """,

    "systemctl status prometheus": f"""● prometheus.service - Prometheus Monitoring System
     Loaded: loaded (/lib/systemd/system/prometheus.service; enabled)
     Active: active (running) since Mon 2024-10-01 00:00:00 UTC; 83 days 14h ago
   Main PID: 9012 (prometheus)
     Memory: 384.0M (limit: 2.0G)
     CPU: 2.8%
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
    print(f"[Mock Prometheus {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
