"""Mock Cisco WLC 9800 SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("WLC_HOSTNAME", "WLC-9800-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Cisco123!")

COMMANDS = {
    "show wlan summary": f"""Number of WLANs: 4

WLAN Profile Name                     SSID                             Status
---- -------------------------------- -------------------------------- ------
1    CORP-EMPLOYEES                   CORP-SECURE                      Enabled
2    GUEST-WIFI                       Guest-Network                    Enabled
3    IOT-DEVICES                      IOT-MGMT                         Enabled
4    VOICE-WIFI                       CORPVOICE                        Enabled
{HOSTNAME}# """,

    "show ap summary": f"""Number of APs: 6

AP Name               Slots  AP Model          Ethernet MAC    Radio MAC       Location
------------------    -----  ----------------  --------------- --------------- --------
AP-FLOOR1-01          3      C9120AXI-B        0050.56.10.0101 0050.56.10.0102 Floor 1
AP-FLOOR1-02          3      C9120AXI-B        0050.56.10.0201 0050.56.10.0202 Floor 1
AP-FLOOR2-01          3      C9120AXI-B        0050.56.10.0301 0050.56.10.0302 Floor 2
AP-FLOOR2-02          3      C9120AXI-B        0050.56.10.0401 0050.56.10.0402 Floor 2
AP-LOBBY-01           2      C9115AXI-B        0050.56.10.0501 0050.56.10.0502 Lobby
AP-ROOF-01            2      C9115AXI-B        0050.56.10.0601 0050.56.10.0602 Rooftop
{HOSTNAME}# """,

    "show wireless client summary": f"""Number of Clients: 87

MAC Address    AP Name             WLAN  State    Protocol Num  Curr_Rate  Bytes_Rx   Bytes_Tx
0050.5601.0001 AP-FLOOR1-01        1     Run      11ax(5GHz)    -/540      2.1G       0.8G
0050.5601.0002 AP-FLOOR1-02        1     Run      11ax(5GHz)    -/540      1.4G       0.5G
0050.5601.0003 AP-FLOOR2-01        2     Run      11ax(2.4GHz)  -/144      0.2G       0.1G
... (84 more)
{HOSTNAME}# """,

    "show wireless rf-tag summary": f"""Number of RF Tags: 3

RF-Tag Name           Description                              Policies
--------------------  ---------------------------------------- --------
HIGH-DENSITY          High density environments (floors)       5GHz-HE/2.4GHz-HE
LOW-DENSITY           Low density (lobby, rooftop)             5GHz-LE/2.4GHz-LE
IOT-ONLY              IoT device RF profile                    2.4GHz-IOT
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
                resp = next((v for k, v in COMMANDS.items() if cmd.lower().startswith(k.lower())), f"% Invalid command: '{cmd}'\r\n{HOSTNAME}# ")
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
    print(f"[Mock WLC {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
