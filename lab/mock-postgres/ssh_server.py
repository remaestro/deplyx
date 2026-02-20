"""Mock PostgreSQL SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("PG_HOSTNAME", "postgres-db-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Postgres123!")

COMMANDS = {
    "psql -l": f"""                                  List of databases
   Name    |  Owner   | Encoding |   Collate   |    Ctype    |   Access privileges  
-----------+----------+----------+-------------+-------------+---------------------
 appdb     | appuser  | UTF8     | en_US.UTF-8 | en_US.UTF-8 | 
 analytics | analyst  | UTF8     | en_US.UTF-8 | en_US.UTF-8 | 
 auth      | authuser | UTF8     | en_US.UTF-8 | en_US.UTF-8 | 
 logs      | loguser  | UTF8     | en_US.UTF-8 | en_US.UTF-8 | 
 postgres  | postgres | UTF8     | en_US.UTF-8 | en_US.UTF-8 | 
 template0 | postgres | UTF8     | en_US.UTF-8 | en_US.UTF-8 | =c/postgres
 template1 | postgres | UTF8     | en_US.UTF-8 | en_US.UTF-8 | =c/postgres
{HOSTNAME}$ """,

    "show connections": f"""PostgreSQL Connection Summary:
  max_connections: 200
  Current connections: 87
  Active queries: 12
  Idle connections: 72
  Idle in transaction: 3
  By database:
    appdb:     45 connections
    analytics: 22 connections
    auth:       8 connections
    logs:      12 connections
{HOSTNAME}$ """,

    "pg_stat_activity": f""" pid  | usename  | application_name |  client_addr  | state  |              query_start               | state
-----+----------+------------------+---------------+---------+---------------------------------------+--------
 123 | appuser  | pgbouncer        | 10.0.1.100    | active  | 2024-12-01 14:22:33.123456+00         | SELECT * FROM orders WHERE id = $1
 456 | appuser  | pgbouncer        | 10.0.1.101    | idle    | 2024-12-01 14:22:32.000000+00         |
 789 | analyst  | psql             | 10.0.1.200    | active  | 2024-12-01 14:22:11.000000+00         | SELECT COUNT(*) FROM events WHERE ...
(87 rows)
{HOSTNAME}$ """,

    "show replication": f"""PostgreSQL Replication Status:
  wal_level: replica
  max_wal_senders: 10
  
  Active replication slots:
  Slot Name              | Active | WAL latency | Replay delay
  ---------------------- | ------ | ----------- | ------------
  pg_replica_01          | t      | 0 bytes     | 0.210 ms
  pg_replica_02          | t      | 0 bytes     | 0.345 ms
  
  Streaming replicas: 2 (both in sync)
{HOSTNAME}$ """,

    "psql -c 'select version()'": f"""                                                               version                                                                
----------------------------------------------------------------------------------------------------------------------------------------
 PostgreSQL 16.2 on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14) 12.2.0, 64-bit
(1 row)
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
                resp = next((v for k, v in COMMANDS.items() if cmd.lower().startswith(k.lower())), f"bash: {cmd}: command not found\r\n{HOSTNAME}$ ")
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
    print(f"[Mock PostgreSQL {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
