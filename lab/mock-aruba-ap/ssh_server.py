"""Mock Aruba AP SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("AP_HOSTNAME", "AP-FLOOR1-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Aruba123!")

COMMANDS = {
    "show ap bss-table": f"""BSSID             RSSi  Ch  ESSID              Clients  Tx Bps   Rx Bps
----------------- ----  --  -----------------  -------  -------  -------
70:10:5c:b0:00:10 -65   6   CORP-SECURE        12       4.2M     1.0M
70:10:5c:b0:00:11 -60   36  CORP-SECURE        18       8.5M     2.4M
70:10:5c:b0:00:12 -70   1   Guest-Network      3        0.8M     0.2M
70:10:5c:b0:00:13 -55   149 Guest-Network      5        1.2M     0.5M
{HOSTNAME}# """,

    "show ap radio-summary": f"""Radio  Band   Channel  TxPwr  EIRP  Mode           Standard
-----  -----  -------  -----  ----  -------------  --------
Radio 0  2.4GHz  6        18dBm  23    Access Point   802.11ax
Radio 1  5GHz    36       20dBm  26    Access Point   802.11ax
Radio 2  5GHz    149      20dBm  26    Access Point   802.11ax (monitor)
{HOSTNAME}# """,

    "show clients": f"""Total Clients: 38

Client MAC        IP Address      ESSID          Radio  Signal  Tx Mbps
-------------     --------------- ---            -----  ------  -------
aa:bb:cc:01:01:01 10.20.0.101     CORP-SECURE    5GHz   -55dBm  540
aa:bb:cc:01:01:02 10.20.0.102     CORP-SECURE    5GHz   -62dBm  270
aa:bb:cc:01:01:03 10.20.0.103     Guest-Network  2.4GHz -71dBm  72
... (35 more clients)
{HOSTNAME}# """,

    "show ap config": f"""AP Name         : {HOSTNAME}
AP Model        : C9120AXI-B
Serial Number   : APC1234500{os.getenv('AP_INDEX','01')}
AP Group        : FLOOR-APS
AP Mode         : Local
Controller IP   : 10.100.0.50
Software Version: 8.10.150.0
Uptime          : 83d 14h 22m
{HOSTNAME}# """,
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
        ch.sendall(f"\r\n{HOSTNAME}# ".encode())
        buf = b""
        while True:
            data = ch.recv(4096)
            if not data: break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                cmd = line.decode("utf-8", errors="ignore").strip().rstrip("\r")
                if not cmd: ch.sendall(f"\r\n{HOSTNAME}# ".encode()); continue
                if cmd in ("exit", "quit"): return
                resp = next((v for k, v in COMMANDS.items() if cmd.lower().startswith(k.lower())), f"Command not found: {cmd}\r\n{HOSTNAME}# ")
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
    print(f"[Mock Aruba AP {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
