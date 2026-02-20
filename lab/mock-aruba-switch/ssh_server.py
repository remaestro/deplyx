"""Mock ArubaOS CX Switch SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("ARUBA_HOSTNAME", "ARUBA-CX-CORE-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Aruba123!")

COMMANDS = {
    "show version": f"""ArubaOS-CX
(c) Copyright 2017-2026 Hewlett Packard Enterprise Development LP
Version   : FL.10.11.0001
Build Date: 2024-03-15 04:12:33 UTC
Build ID  : ArubaOS-CX:FL.10.11.0001:bbb123

Platform  : 6400 Chassis
ROM Version: FL.01.02.0006
Serial Number: SG12345678

{HOSTNAME}# """,

    "show interfaces": f"""Interface 1/1/1 is up
  Description: UPLINK-CORE-SWITCH
  Hardware: Ethernet, MAC Address: 70:10:5c:ab:cd:01
  MTU 9198
  Full-duplex, 25Gb/s
  Auto-Negotiation is off

Interface 1/1/2 is up
  Description: SERVER-RACK-A
  Hardware: Ethernet, MAC Address: 70:10:5c:ab:cd:02
  MTU 9198
  Full-duplex, 10Gb/s

Interface 1/1/3 is up
  Description: SERVER-RACK-B
  Hardware: Ethernet, MAC Address: 70:10:5c:ab:cd:03
  Full-duplex, 10Gb/s

{HOSTNAME}# """,

    "show vlans": f"""VLAN  Name                 Status  Reason  Type      Interfaces
----  -------------------- ------  ------  --------- --------------------
1     default              up      ok      static
10    SERVERS              up      ok      static    1/1/2, 1/1/3
20    STORAGE              up      ok      static    1/1/4, 1/1/5
30    MANAGEMENT           up      ok      static    1/1/1
40    VOICE                up      ok      static    1/1/6
100   BACKUP               up      ok      static    1/1/7
{HOSTNAME}# """,

    "show spanning-tree": f"""MST Instance    : 0
Root ID         : Priority 4096 / MAC 70:10:5c:00:01:00
Bridge ID       : Priority 8192 / MAC 70:10:5c:ab:cd:00
Root Port       : 1/1/1
Root Path Cost  : 2000

Port            State           Role     Cost  Priority  Type
-----------     -----           ----     ----  --------  ----
1/1/1           Forwarding      ROOT     2000  128       P2P
1/1/2           Forwarding      DESGN    20000 128       P2P
1/1/3           Forwarding      DESGN    20000 128       P2P
1/1/4           Forwarding      DESGN    20000 128       P2P
{HOSTNAME}# """,

    "show lldp info remote-device": f"""Local Port | ChassisType | ChassisId                 | PortType | PortId       | SysName
---------- | ----------- | ------------------------- | -------- | ------------ | -------
1/1/1      | mac-address | e0:d9:e3:01:02:03         | if-name  | Eth1/3       | CORE-SPINE-01
1/1/2      | mac-address | 00:50:56:b0:01:01         | if-name  | ens192       | ESXI-HOST-01
1/1/3      | mac-address | 00:50:56:b0:02:01         | if-name  | ens192       | ESXI-HOST-02
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
    print(f"[Mock Aruba CX {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
