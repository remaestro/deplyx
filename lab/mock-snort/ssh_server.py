"""Mock Snort IDS SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("IDS_HOSTNAME", "snort-ids-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Snort123!")

COMMANDS = {
    "snort --version": f"""   ,,_     -*> Snort! <*-
  o"  )~  Version 3.1.74.0 GRE (Build 20240315) by Martin Roesch & The Snort Team
   ''''    http://www.snort.org/contact#team
           Copyright (C) 2014-2024 Cisco and/or its affiliates.
{HOSTNAME}$ """,

    "show alerts": f"""Recent Alerts (last 50):
[2024-12-01 14:22:33] [PRIORITY:2] MALWARE-CNC Win.Trojan.Emotet variant outbound connection
  SRC: 10.0.1.105:49132 -> DST: 45.33.32.156:443  PROTO:TCP
  RULE: 2037771 CLASS: A Network Trojan was detected

[2024-12-01 14:18:11] [PRIORITY:1] ET SCAN Nmap Scripting Engine User-Agent Detected
  SRC: 172.16.50.10:39200 -> DST: 10.0.1.0/24:*  PROTO:TCP
  RULE: 2018489 CLASS: Attempted Information Leak

[2024-12-01 13:55:02] [PRIORITY:3] ET POLICY SSH session in progress on non-standard port
  SRC: 10.0.1.120:55024 -> DST: 10.0.2.50:2222  PROTO:TCP

Total: 127 alerts in last 24h (42 high, 63 medium, 22 low)
{HOSTNAME}$ """,

    "show stats": f"""Snort Statistics:
  Runtime: 30 days, 14 hours, 22 minutes
  Packets analyzed: 4,872,344,120
  Packets dropped: 12,840 (0.00%)
  Alerts generated: 3,847
  Blocked packets: 284
  Active rules: 32,841
  Rule updates: Last applied 2024-12-01 02:00:00 UTC

Interface Statistics:
  eth0 (MONITORING): 98,234 pps / 8.2 Gbps
  eth1 (INLINE): 12,445 pps / 1.0 Gbps
{HOSTNAME}$ """,

    "show blocked-hosts": f"""Blocked Hosts (Dynamic Block List):
IP Address       Block Reason                    Expires          Hits
---------------  ------------------------------  ---------------  ----
45.33.32.156     CNC-Emotet-variant              2024-12-02 14h   3
185.220.101.8    TOR-Exit-Node-Traffic           permanent        47
192.168.50.99    Port-Scan-Internal              2024-12-01 18h   1,204
194.165.16.35    Exploit-Kit-Traffic             permanent        12
{HOSTNAME}$ """,

    "show interfaces": f"""Snort monitored interfaces:
  eth0  LISTENING  MTU:9000  Speed:10Gbps  PCAP-mode   RX:4.8B pkts  [SPAN-port]
  eth1  INLINE     MTU:1500  Speed:1Gbps   NFQ-mode    RX:0.4B pkts  [GW-mirror]
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
    print(f"[Mock Snort IDS {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
