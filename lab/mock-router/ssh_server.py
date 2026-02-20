"""Mock Cisco ISR Router SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("ROUTER_HOSTNAME", "ISR-EDGE-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Cisco123!")

SHOW_VERSION = f"""Cisco IOS XE Software, Version 17.09.04a
Cisco IOS Software [Cupertino], ISR4451/K9 Software (X86_64LINUX_IOSD-UNIVERSALK9-M)
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2024 by Cisco Systems, Inc.
Compiled Tue 21-May-24 03:38 by mcpre

Cisco ISR4451-X/K9 (1RU) processor with 1687541K/6147K bytes of memory.
Processor board ID FGL221511TY
2 Gigabit Ethernet interfaces
2 Ten Gigabit Ethernet interfaces
32768K bytes of non-volatile configuration memory.
16777216K bytes of physical memory.

Router uptime is 83 days, 14 hours, 22 minutes
{HOSTNAME}# """

SHOW_IP_ROUTE = f"""Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP
       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area

Gateway of last resort is 203.0.113.1 to network 0.0.0.0

S*    0.0.0.0/0 [1/0] via 203.0.113.1
      10.0.0.0/8 is variably subnetted
C        10.0.1.0/24 is directly connected, GigabitEthernet0/0/0
L        10.0.1.1/32 is directly connected, GigabitEthernet0/0/0
C        10.0.2.0/24 is directly connected, GigabitEthernet0/0/1
B        192.168.100.0/24 [20/0] via 10.0.2.2, 2w3d
O        172.16.0.0/16 [110/200] via 10.0.1.2, 83d14h
{HOSTNAME}# """

SHOW_BGP = f"""BGP table version is 88, local router ID is 203.0.113.5
Status codes: s suppressed, d damped, h history, * valid, > best
              i - internal, r RIB-failure, S Stale, m multipath

     Network          Next Hop            Metric LocPrf Weight Path
 *>  0.0.0.0          203.0.113.1              0             0 7922 i
 *>  192.168.100.0    10.0.2.2                 0         32768 ?
 *>  172.16.0.0/16    10.0.1.2                 0         32768 ?

Total number of prefixes 3
{HOSTNAME}# """

SHOW_OSPF = f"""Neighbor ID     Pri   State           Dead Time   Address         Interface
10.0.1.2          1   FULL/DR         00:00:37    10.0.1.2        GigabitEthernet0/0/0
10.0.2.2          1   FULL/BDR        00:00:34    10.0.2.2        GigabitEthernet0/0/1
{HOSTNAME}# """

SHOW_NAT = f"""Pro Inside global      Inside local       Outside local      Outside global
tcp 203.0.113.5:1024   10.0.1.100:1024    8.8.8.8:53         8.8.8.8:53
tcp 203.0.113.5:1025   10.0.1.101:1025    1.1.1.1:443        1.1.1.1:443
udp 203.0.113.5:5353   10.0.1.102:5353    8.8.4.4:53         8.8.4.4:53

Total active translations: 3 (1 static, 2 dynamic; 1 extended)
{HOSTNAME}# """

SHOW_ACL = f"""Standard IP access list MANAGEMENT-ACCESS
    10 permit 10.0.0.0, wildcard bits 0.255.255.255 (288 matches)
    20 deny   any (0 matches)

Extended IP access list OUTBOUND-FILTER
    10 permit ip 10.0.1.0 0.0.0.255 any
    20 deny   ip any any log

{HOSTNAME}# """

COMMAND_MAP = {
    "show version": SHOW_VERSION,
    "show ip route": SHOW_IP_ROUTE,
    "show ip bgp summary": SHOW_BGP,
    "show ip ospf neighbor": SHOW_OSPF,
    "show ip nat translations": SHOW_NAT,
    "show access-lists": SHOW_ACL,
    "show interfaces": f"GigabitEthernet0/0/0 is up, line protocol is up\n  Hardware: Gigabit Ethernet, address: 0050.5600.0201\n  Internet address is 10.0.1.1/24\n  MTU 1500 bytes, BW 1000000 Kbit\n  5 minute input rate 24000 bits/sec, 30 packets/sec\n{HOSTNAME}# ",
    "terminal length 0": "",
    "terminal width": "",
}


class MockSSH(paramiko.ServerInterface):
    def check_channel_request(self, kind, chanid): return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
    def check_auth_password(self, username, password): return paramiko.AUTH_SUCCESSFUL if username == SSH_USER and password == SSH_PASS else paramiko.AUTH_FAILED
    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes): return True
    def check_channel_shell_request(self, channel): return True
    def check_channel_exec_request(self, channel, command): return True
    def get_allowed_auths(self, username): return "password,publickey"
    def check_auth_publickey(self, username, key): return paramiko.AUTH_SUCCESSFUL


def handle_client(sock, addr):
    t = paramiko.Transport(sock)
    t.add_server_key(HOST_KEY)
    try:
        t.start_server(server=MockSSH())
    except paramiko.SSHException:
        try: sock.close()
        except Exception: pass
        return
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
                if cmd in ("exit", "quit", "logout"): ch.sendall(b"\r\nBye!\r\n"); return
                resp = next((v for k, v in COMMAND_MAP.items() if cmd.lower().startswith(k.lower())), f"% Invalid command: '{cmd}'\r\n{HOSTNAME}# ")
                if resp == "":
                    ch.sendall(f"{cmd}\r\n{HOSTNAME}# ".encode())
                else:
                    ch.sendall(f"{cmd}\r\n{resp}\r\n".encode())
    except Exception: pass
    finally:
        try: ch.close()
        except: pass
        t.close()


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", SSH_PORT)); s.listen(5)
    print(f"[Mock ISR Router {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
