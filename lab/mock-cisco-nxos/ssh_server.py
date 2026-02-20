"""Mock Cisco NX-OS SSH server (Nexus 9000)."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("NXOS_HOSTNAME", "NXOS-DC1-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Cisco123!")

SHOW_VERSION = f"""Cisco Nexus Operating System (NX-OS) Software
TAC support: http://www.cisco.com/tac
Documents: http://www.cisco.com/en/US/products/ps9372/tsd_products_support_serie...
Copyright (c) 2002-2026, Cisco Systems, Inc. All rights reserved.

Software
  BIOS: version 05.39
  NXOS: version 10.3(3)F
  BIOS compile time:  05/29/2023
  NXOS image file is: bootflash:///nxos64-cs.10.3.3.F.bin

Hardware
  cisco Nexus9000 C9364C-GX Chassis
  Intel(R) Xeon(R) CPU E5-2637 v2 @ 3.50GHz with 24576 kB of memory.
  Processor Board ID SAL2018DAG2

  Device name: {HOSTNAME}
  bootflash:   56623104 kB
Kernel uptime is 183 day(s), 6 hour(s), 15 minute(s), 22 second(s)

{HOSTNAME}# """

SHOW_INTERFACES = f"""Ethernet1/1 is up
  Hardware: 100/1000/10000/100000 Ethernet, address: 0050.5600.0101
  Description: UPLINK-SPINE-01
  MTU 9216 bytes, BW 100000000 Kbit, DLY 10 usec
  reliability 255/255, txload 1/255, rxload 1/255
  Encapsulation ARPA, medium is broadcast
  full-duplex, 100 Gb/s, media type is 100G

Ethernet1/2 is up
  Hardware: 100/1000/10000/100000 Ethernet, address: 0050.5600.0102
  Description: SERVER-ESX-01
  MTU 9216 bytes,  BW 25000000 Kbit
  full-duplex, 25 Gb/s, media type is 25G

Ethernet1/3 is up
  Hardware: 100/1000/10000/100000 Ethernet, address: 0050.5600.0103
  Description: SERVER-ESX-02
  MTU 9216 bytes,  BW 25000000 Kbit
  full-duplex, 25 Gb/s, media type is 25G

mgmt0 is up
  Hardware: GigabitEthernet, address: 0050.5600.0100
  Description: OOB-MANAGEMENT
  Internet address is 172.16.99.10/24

{HOSTNAME}# """

SHOW_VLAN = f"""VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    
10   SERVERS                          active    Eth1/2, Eth1/3
20   STORAGE                          active    Eth1/4
30   VMOTION                          active    Eth1/5
40   MANAGEMENT                       active    Eth1/6
100  DATABASE                         active    
200  BACKUP                           active    

{HOSTNAME}# """

SHOW_BGP = f"""BGP summary information for VRF default, address family IPv4 Unicast
BGP router identifier 10.0.255.10, local AS number 65010
BGP table version is 245, IPv4 Unicast config peers 2, capable peers 2

Neighbor        V    AS    MsgRcvd    MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
10.0.255.1      4 65000      88450      88449      245    0    0 183d06h          24
10.0.255.2      4 65000      88445      88443      245    0    0 183d06h          24

{HOSTNAME}# """

SHOW_VRF = f"""VRF-Name                           VRF-ID State   Reason
default                                 1 Up      --
management                              2 Up      --
PROD                                    3 Up      --
STORAGE                                 4 Up      --

{HOSTNAME}# """

COMMAND_MAP = {
    "show version": SHOW_VERSION,
    "show interface": SHOW_INTERFACES,
    "show vlan": SHOW_VLAN,
    "show bgp summary": SHOW_BGP,
    "show vrf": SHOW_VRF,
    "show running-config": f"! NX-OS Running Config\nhostname {HOSTNAME}\n\nfeature bgp\nfeature ospf\nfeature vpc\n\nvlan 10\n  name SERVERS\nvlan 20\n  name STORAGE\n\n{HOSTNAME}# ",
    "terminal length 0": "",
    "terminal width 511": "",
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
    print(f"[Mock NX-OS {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
