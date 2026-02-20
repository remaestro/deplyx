"""Mock Redis SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("REDIS_HOSTNAME", "redis-cache-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Redis123!")

COMMANDS = {
    "redis-cli info": f"""# Server
redis_version:7.2.3
redis_git_sha1:00000000
os:Linux 6.1.0 x86_64
arch_bits:64
tcp_port:6379
uptime_in_seconds:7205843
uptime_in_days:83
hz:10
aof_enabled:1

# Clients
connected_clients:48
blocked_clients:0
tracking_clients:0

# Memory
used_memory:512483328
used_memory_human:488.81M
used_memory_rss:536870912
used_memory_peak:524288000
used_memory_peak_human:500.00M
maxmemory:4294967296
maxmemory_human:4.00G
maxmemory_policy:allkeys-lru

# Stats
total_connections_received:1247893
total_commands_processed:489247810
instantaneous_ops_per_sec:4820
total_net_input_bytes:48924781000
total_net_output_bytes:122371952500
rejected_connections:0
expired_keys:124500
evicted_keys:0

# Replication
role:master
connected_slaves:2
slave0:ip=10.0.1.111,port=6379,state=online,offset=48924781000,lag=1
slave1:ip=10.0.1.112,port=6379,state=online,offset=48924781000,lag=0

# Keyspace
db0:keys=125847,expires=44223,avg_ttl=86400000
db1:keys=4512,expires=4512,avg_ttl=3600000
db2:keys=892,expires=0,avg_ttl=0
{HOSTNAME}$ """,

    "redis-cli dbsize": f"""(integer) 131251
{HOSTNAME}$ """,

    "redis-cli config get maxmemory": f"""1) "maxmemory"
2) "4294967296"
{HOSTNAME}$ """,

    "redis-cli config get": f"""  1) "maxmemory"
  2) "4294967296"
  3) "maxmemory-policy"
  4) "allkeys-lru"
  5) "save"
  6) "3600 1 300 100 60 10000"
  7) "appendonly"
  8) "yes"
  9) "bind"
 10) "0.0.0.0"
 11) "protected-mode"
 12) "yes"
{HOSTNAME}$ """,

    "redis-cli client list": f"""id=1008 addr=10.0.1.100:54210 laddr=10.0.1.110:6379 fd=18 name=app-session age=0 idle=0 flags=N db=0 sub=0 psub=0 ssub=0 multi=-1 watch=0 qbuf=26 qbuf-free=20448 argv-mem=10 multi-mem=0 tot-mem=22298 rbs=16384 rbp=0 obl=0 oll=0 omem=0 events=r cmd=get|GET user=default library-name=jedis library-ver=3.9.0 resp=2
id=1009 addr=10.0.1.101:47832 laddr=10.0.1.110:6379 fd=19 name=cache-worker age=0 idle=0 flags=N db=0 sub=0 psub=0 psub=0 ssub=0 multi=-1 watch=0 qbuf=0 qbuf-free=0 argv-mem=10 multi-mem=0 tot-mem=22298 rbs=16384 rbp=16384 obl=0 oll=0 omem=0 events=r cmd=set|SET user=default library-name=ioredis library-ver=5.3.2 resp=2
(48 clients)
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
    print(f"[Mock Redis {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
