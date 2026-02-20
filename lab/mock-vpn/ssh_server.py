"""Mock StrongSwan VPN SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("VPN_HOSTNAME", "vpn-gateway-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "VPN123!")

COMMANDS = {
    "ipsec status": f"""Security Associations (4 up, 0 connecting):
  REMOTE-OFFICE[14]: ESTABLISHED 6 days ago, 203.0.113.5[vpn.corp.com]...198.51.100.20[remote.corp.com]
  BACKUP-DC[8]: ESTABLISHED 83 days ago, 203.0.113.5[vpn.corp.com]...198.51.100.50[dc-backup.corp.com]
  PARTNER-VPN[3]: ESTABLISHED 2 days ago, 203.0.113.5[vpn.corp.com]...198.51.100.80[partner.example.com]
  ROADWARRIOR-POOL: ESTABLISHED 1 hour ago, 203.0.113.5...dynamic (12 clients)
{HOSTNAME}$ """,

    "ipsec statusall": f"""Status of IKE charon daemon (strongSwan 5.9.14, Linux 6.1.0):
  uptime: 83 days, since Dec 01 00:00:00 2024
  worker threads: 16 of 16 idle, 7/3/1/0 busy
  job queue: 0/0/0/0, scheduled: 22

Listening IP addresses:
  203.0.113.5
  10.100.0.60

Connections:
   REMOTE-OFFICE:  203.0.113.5...198.51.100.20  IKEv2, dpddelay=30s
   BACKUP-DC:  203.0.113.5...198.51.100.50  IKEv2, dpddelay=30s
   ROADWARRIOR-POOL:  203.0.113.5...%any  IKEv2
   
Security Associations (4 up, 0 connecting):
  REMOTE-OFFICE[14]: ESTABLISHED 6 days ago
    203.0.113.5[vpn.corp.com]...198.51.100.20[remote.corp.com]
    AES_CBC-256/HMAC_SHA2_256_128/PRF_HMAC_SHA2_256/CURVE_25519
    CHILD:  10.0.1.0/24 === 192.168.100.0/24
{HOSTNAME}$ """,

    "show connections": f"""Active VPN Connections:
  Site-to-Site:
    REMOTE-OFFICE  203.0.113.5 <=> 198.51.100.20  UP  6d02h  15.2G/8.4G
    BACKUP-DC      203.0.113.5 <=> 198.51.100.50  UP  83d14h  4.1G/3.8G
    PARTNER-VPN    203.0.113.5 <=> 198.51.100.80  UP  2d03h   0.5G/0.3G
  Remote Access:
    ROADWARRIOR-POOL  12 clients connected
{HOSTNAME}$ """,

    "show tunnels": f"""Tunnel Name        Local IP       Remote IP        State   Uptime   In/Out
-----------------  -------------- ---------------  ------  -------  ----------
REMOTE-OFFICE      10.0.1.0/24    192.168.100.0/24 UP      6d02h    15.2G/8.4G
BACKUP-DC          10.0.1.0/24    172.16.0.0/16    UP      83d14h   4.1G/3.8G
PARTNER-VPN        10.10.0.0/24   10.200.0.0/24    UP      2d03h    0.5G/0.3G
{HOSTNAME}$ """,

    "ip route": f"""default via 203.0.113.1 dev eth0 proto static
10.0.1.0/24 via 10.100.0.1 dev eth1
192.168.100.0/24 via 198.51.100.20 dev vti0 proto static
172.16.0.0/16 via 198.51.100.50 dev vti1 proto static
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
                resp = next((v for k, v in COMMANDS.items() if cmd.lower().startswith(k.lower())), f"command not found: {cmd}\r\n{HOSTNAME}$ ")
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
    print(f"[Mock VPN {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
