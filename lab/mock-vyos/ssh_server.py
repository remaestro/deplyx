"""Mock VyOS Router SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("VYOS_HOSTNAME", "vyos-edge-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "vyos")
SSH_PASS = os.getenv("SSH_PASS", "VyOS123!")

COMMANDS = {
    "show interfaces": f"""Codes: S - State, L - Link, u - Up, D - Down, A - Admin Down
Interface        IP Address                        S/L  Description
---------        ----------                        ---  -----------
eth0             203.0.113.10/30                   u/u  WAN-UPLINK
eth1             10.0.1.1/24                       u/u  LAN-INTERNAL
eth2             10.10.0.1/24                      u/u  DMZ-SERVERS
lo               127.0.0.1/8                       u/u
                 ::1/128
{HOSTNAME}:~$ """,

    "show ip route": f"""Codes: K - kernel route, C - connected, S - static, R - RIP, O - OSPF
       B - BGP, > - selected route, * - FIB route, ~ - kernel installed

S>* 0.0.0.0/0 [1/0] via 203.0.113.9, eth0, 83d14h22m
C>* 10.0.1.0/24 is directly connected, eth1, 83d14h22m
C>* 10.10.0.0/24 is directly connected, eth2, 83d14h22m
B>* 192.168.0.0/16 [20/0] via 10.0.1.2, 03w5d
{HOSTNAME}:~$ """,

    "show bgp summary": f"""IPv4 Unicast Summary:
BGP router identifier 203.0.113.10, local AS number 65001
...
Neighbor        V         AS MsgRcvd MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd
10.0.1.2        4      65000   14220   14219        0    0    0 03w5d06h           12
{HOSTNAME}:~$ """,

    "show firewall": f"""Rulesets:
  WAN-IN (8 rules)
    1 - Drop INVALID
    2 - Accept ESTABLISHED/RELATED
    5 - Accept ICMP
    10 - Accept DNS from 10.0.1.0/24
    100 - Drop all
  LAN-OUT (3 rules)
    1 - Accept ESTABLISHED
    10 - Accept all from 10.0.1.0/24
    100 - Drop all
{HOSTNAME}:~$ """,

    "show nat": f"""rule 100 (MASQUERADE on eth0)
  type masquerade
  outbound-interface eth0
  source address 10.0.1.0/24
  translation address masquerade

rule 200 (DNAT - web server)
  type destination
  inbound-interface eth0
  destination port 80,443
  translation address 10.10.0.10
{HOSTNAME}:~$ """,

    "show vpn ipsec sa": f"""Connection                 State    Uptime    Bytes In/Out    Packets In/Out
REMOTE-OFFICE-VPN          up       6d02h     15.2G/8.4G      11M/8.4M
BACKUP-DC-VPN              up       83d14h    4.1G/3.8G       3.2M/2.9M
PARTNER-EXTRANET           down     -         -               -
{HOSTNAME}:~$ """,
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
        ch.sendall(f"\r\n{HOSTNAME}:~$ ".encode())
        buf = b""
        while True:
            data = ch.recv(4096)
            if not data: break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                cmd = line.decode("utf-8", errors="ignore").strip().rstrip("\r")
                if not cmd: ch.sendall(f"\r\n{HOSTNAME}:~$ ".encode()); continue
                if cmd in ("exit", "quit"): return
                resp = next((v for k, v in COMMANDS.items() if cmd.lower().startswith(k.lower())), f"Command not found: {cmd}\r\n{HOSTNAME}:~$ ")
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
    print(f"[Mock VyOS {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
