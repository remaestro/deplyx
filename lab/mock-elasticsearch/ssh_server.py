"""Mock Elasticsearch SSH server (with bonus HTTP healthcheck)."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("ES_HOSTNAME", "elastic-node-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Elastic123!")

COMMANDS = {
    "curl localhost:9200/_cat/indices": f"""green  open   app-logs-2024.12.01     3 1 2847293 0  4.8gb  2.4gb
green  open   app-logs-2024.11.30     3 1 3124847 0  5.2gb  2.6gb
green  open   metrics-2024.12.01      1 1  847234 0  1.2gb  0.6gb
green  open   security-events         1 1  124500 0  0.3gb  0.1gb
yellow open   .kibana_1               1 0     248 0  1.5mb  1.5mb
{HOSTNAME}$ """,

    "curl localhost:9200/_cluster/health": f"""{{
  "cluster_name" : "prod-cluster",
  "status" : "green",
  "timed_out" : false,
  "number_of_nodes" : 3,
  "number_of_data_nodes" : 3,
  "active_primary_shards" : 24,
  "active_shards" : 48,
  "relocating_shards" : 0,
  "initializing_shards" : 0,
  "unassigned_shards" : 0,
  "delayed_unassigned_shards" : 0,
  "active_shards_percent_as_number" : 100.0
}}
{HOSTNAME}$ """,

    "curl localhost:9200/_nodes/stats": f"""{{
  "_nodes": {{ "total": 3, "successful": 3, "failed": 0 }},
  "cluster_name": "prod-cluster",
  "nodes": {{
    "node1": {{
      "name": "es-node-01",
      "transport_address": "10.0.1.121:9300",
      "roles": ["master", "data", "ingest"],
      "indices": {{
        "docs": {{ "count": 7143874, "deleted": 0 }},
        "store": {{ "size_in_bytes": 11073741824 }},
        "indexing": {{ "index_total": 12847293, "index_current": 48 }},
        "search": {{ "query_total": 48924781, "query_current": 3 }}
      }},
      "jvm": {{ "mem": {{ "heap_used_percent": 42 }}, "uptime_in_millis": 7205843000 }}
    }}
  }}
}}
{HOSTNAME}$ """,

    "systemctl status elasticsearch": f"""● elasticsearch.service - Elasticsearch
     Loaded: loaded (/lib/systemd/system/elasticsearch.service; enabled)
     Active: active (running) since Mon 2024-10-01 00:00:00 UTC; 83 days 14h ago
   Main PID: 1234 (java)
      Tasks: 84
     Memory: 8.2G
      CGroup: /system.slice/elasticsearch.service
              └─1234 /usr/share/elasticsearch/jdk/bin/java -Xms4g -Xmx4g ...
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
    print(f"[Mock Elasticsearch {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
