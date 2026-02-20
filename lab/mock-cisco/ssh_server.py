"""Mock Cisco IOS SSH server using FakeNOS.

Creates a fake Cisco IOS device that responds to NAPALM driver commands
over SSH. This allows the deplyx CiscoConnector to connect and sync
device facts, interfaces, VLANs, and IPs — exactly like a real switch.
"""

import os
import threading
import time
import signal
import sys

# FakeNOS is complex to set up; instead we use paramiko to create
# a simple SSH server that responds to the show commands NAPALM sends.
import paramiko
import socket

HOST_KEY = paramiko.RSAKey.generate(2048)

HOSTNAME = os.getenv("CISCO_HOSTNAME", "SW-DC1-CORE")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Cisco123!")

# --- Mock command outputs ---

SHOW_VERSION = f"""{HOSTNAME} uptime is 45 days, 12 hours, 33 minutes
System returned to ROM by power-on
System image file is "flash:cat9k_iosxe.17.09.04a.SPA.bin"

Cisco IOS XE Software, Version 17.09.04a
Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4a
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2026 by Cisco Systems, Inc.

ROM: IOS-XE ROMMON
BOOTLDR: System Bootstrap, Version 17.9.4a

{HOSTNAME} uptime is 45 days, 12 hours, 33 minutes
Uptime for this control processor is 45 days, 12 hours, 35 minutes
System returned to ROM by power-on

{HOSTNAME}#"""

SHOW_INTERFACES = f"""GigabitEthernet0/0 is up, line protocol is up
  Hardware is iGbE, address is 0050.5600.0001 (bia 0050.5600.0001)
  Description: UPLINK-TO-FW-DC1
  Internet address is 10.0.0.2/24
  MTU 1500 bytes, BW 1000000 Kbit/sec, DLY 10 usec,
     reliability 255/255, txload 1/255, rxload 1/255
  Full-duplex, 1000Mb/s, media type is RJ45
  input flow-control is off, output flow-control is unsupported
  Last input 00:00:00, output 00:00:00, output hang never
  5 minute input rate 1234000 bits/sec, 892 packets/sec
  5 minute output rate 987000 bits/sec, 654 packets/sec
GigabitEthernet0/1 is up, line protocol is up
  Hardware is iGbE, address is 0050.5600.0002 (bia 0050.5600.0002)
  Description: SERVER-VLAN-10
  Internet address is 10.0.10.1/24
  MTU 1500 bytes, BW 1000000 Kbit/sec, DLY 10 usec,
     reliability 255/255, txload 1/255, rxload 1/255
  Full-duplex, 1000Mb/s, media type is RJ45
GigabitEthernet0/2 is up, line protocol is up
  Hardware is iGbE, address is 0050.5600.0003 (bia 0050.5600.0003)
  Description: DMZ-VLAN-20
  Internet address is 10.0.20.1/24
  MTU 1500 bytes, BW 1000000 Kbit/sec, DLY 10 usec,
     reliability 255/255, txload 1/255, rxload 1/255
  Full-duplex, 1000Mb/s, media type is RJ45
GigabitEthernet0/3 is administratively down, line protocol is down
  Hardware is iGbE, address is 0050.5600.0004 (bia 0050.5600.0004)
  Description: SPARE
  MTU 1500 bytes, BW 1000000 Kbit/sec, DLY 10 usec,
     reliability 255/255, txload 0/255, rxload 0/255
  Auto-duplex, Auto-speed, media type is RJ45
Vlan1 is up, line protocol is up
  Hardware is EtherSVI, address is 0050.5600.0010 (bia 0050.5600.0010)
  Internet address is 10.0.99.1/24
  MTU 1500 bytes, BW 1000000 Kbit/sec, DLY 10 usec,
     reliability 255/255, txload 1/255, rxload 1/255
{HOSTNAME}#"""

SHOW_VLAN = f"""VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Gi0/3
10   SERVERS                          active    Gi0/1
20   DMZ                              active    Gi0/2
30   MANAGEMENT                       active
99   NATIVE                           active
100  DATABASE                         active
200  BACKUP                           active

VLAN Type  SAID       MTU   Parent RingNo BridgeNo Stp  BrdgMode Trans1 Trans2
---- ----- ---------- ----- ------ ------ -------- ---- -------- ------ ------
1    enet  100001     1500  -      -      -        -    -        0      0
10   enet  100010     1500  -      -      -        -    -        0      0
20   enet  100020     1500  -      -      -        -    -        0      0
30   enet  100030     1500  -      -      -        -    -        0      0
99   enet  100099     1500  -      -      -        -    -        0      0
100  enet  100100     1500  -      -      -        -    -        0      0
200  enet  100200     1500  -      -      -        -    -        0      0
{HOSTNAME}#"""

SHOW_RUNNING = f"""Building configuration...

Current configuration : 4521 bytes
!
version 17.9
service timestamps debug datetime msec
service timestamps log datetime msec
!
hostname {HOSTNAME}
!
boot-start-marker
boot-end-marker
!
enable secret 9 $9$xxxx
!
aaa new-model
aaa authentication login default local
!
ip domain-name deplyx.lab
ip name-server 10.0.0.53
!
interface GigabitEthernet0/0
 description UPLINK-TO-FW-DC1
 ip address 10.0.0.2 255.255.255.0
 no shutdown
!
interface GigabitEthernet0/1
 description SERVER-VLAN-10
 switchport access vlan 10
 switchport mode access
 no shutdown
!
interface GigabitEthernet0/2
 description DMZ-VLAN-20
 switchport access vlan 20
 switchport mode access
 no shutdown
!
interface GigabitEthernet0/3
 description SPARE
 shutdown
!
interface Vlan1
 ip address 10.0.99.1 255.255.255.0
 no shutdown
!
interface Vlan10
 ip address 10.0.10.1 255.255.255.0
 no shutdown
!
interface Vlan20
 ip address 10.0.20.1 255.255.255.0
 no shutdown
!
interface Vlan30
 ip address 10.0.30.1 255.255.255.0
 no shutdown
!
ip route 0.0.0.0 0.0.0.0 10.0.0.1
!
line vty 0 4
 transport input ssh
!
end
{HOSTNAME}#"""

# NAPALM IOS "show vlan brief" — condensed single-table output.
# Must be defined BEFORE "show vlan" so the startswith() lookup matches the
# longer command first when NAPALM sends 'show vlan brief'.
SHOW_VLAN_BRIEF = f"""VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Gi0/3
10   SERVERS                          active    Gi0/1
20   DMZ                              active    Gi0/2
30   MANAGEMENT                       active
99   NATIVE                           active
100  DATABASE                         active
200  BACKUP                           active
{HOSTNAME}#"""

# NAPALM sends specific commands — we map them all
COMMAND_MAP = {
    "show version": SHOW_VERSION,
    "show interfaces": SHOW_INTERFACES,
    "show vlan brief": SHOW_VLAN_BRIEF,
    "show vlan": SHOW_VLAN,
    "show running-config": SHOW_RUNNING,
    "show ip interface brief": f"""Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     10.0.0.2        YES NVRAM  up                    up
GigabitEthernet0/1     10.0.10.1       YES NVRAM  up                    up
GigabitEthernet0/2     10.0.20.1       YES NVRAM  up                    up
GigabitEthernet0/3     unassigned      YES NVRAM  administratively down down
Vlan1                  10.0.99.1       YES NVRAM  up                    up
{HOSTNAME}#""",
    "show ip arp": f"""Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  10.0.0.1             12   0050.5600.f001  ARPA   GigabitEthernet0/0
Internet  10.0.0.2              -   0050.5600.0001  ARPA   GigabitEthernet0/0
Internet  10.0.10.100           5   0050.5600.a001  ARPA   GigabitEthernet0/1
Internet  10.0.10.101           3   0050.5600.a002  ARPA   GigabitEthernet0/1
Internet  10.0.20.100           8   0050.5600.b001  ARPA   GigabitEthernet0/2
{HOSTNAME}#""",
    "show mac address-table": f"""          Mac Address Table
-------------------------------------------
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
  10    0050.5600.a001    DYNAMIC     Gi0/1
  10    0050.5600.a002    DYNAMIC     Gi0/1
  20    0050.5600.b001    DYNAMIC     Gi0/2
   1    0050.5600.f001    DYNAMIC     Gi0/0
{HOSTNAME}#""",
    "show cdp neighbors": f"""Capability Codes: R - Router, T - Trans Bridge, B - Source Route Bridge
                  S - Switch, H - Host, I - IGMP, r - Repeater, P - Phone

Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
FW-DC1-01        Gi0/0             178              R S   PA-850    Eth1/1
SW-DC1-ACC01     Gi0/1             145              S     WS-C2960  Gi0/1
SW-DC1-ACC02     Gi0/2             145              S     WS-C2960  Gi0/1
{HOSTNAME}#""",
    "terminal length 0": "",
    "terminal width 511": "",
}


class MockSSHServer(paramiko.ServerInterface):
    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        if username == SSH_USER and password == SSH_PASS:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        # NAPALM/netmiko requests a PTY before invoking the shell on IOS devices.
        # Must return True or the channel is closed immediately after auth.
        return True

    def check_channel_shell_request(self, channel):
        return True

    def check_channel_exec_request(self, channel, command):
        return True

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_auth_publickey(self, username, key):
        return paramiko.AUTH_SUCCESSFUL


def handle_client(client_socket, address):
    transport = paramiko.Transport(client_socket)
    transport.add_server_key(HOST_KEY)
    server = MockSSHServer()

    try:
        transport.start_server(server=server)
    except paramiko.SSHException:
        client_socket.close()
        return

    channel = transport.accept(30)
    if channel is None:
        transport.close()
        return

    try:
        # Send initial prompt
        channel.sendall(f"\r\n{HOSTNAME}#".encode())

        buf = b""
        while True:
            try:
                data = channel.recv(4096)
                if not data:
                    break
                buf += data

                # Process complete lines
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    cmd = line.decode("utf-8", errors="ignore").strip().rstrip("\r")
                    if not cmd:
                        channel.sendall(f"\r\n{HOSTNAME}#".encode())
                        continue

                    if cmd in ("exit", "quit", "logout"):
                        channel.sendall(b"\r\nBye!\r\n")
                        channel.close()
                        return

                    # Find matching command
                    response = None
                    for pattern, output in COMMAND_MAP.items():
                        if cmd.lower().startswith(pattern.lower()):
                            response = output
                            break

                    if response is None:
                        response = f"% Unknown command: '{cmd}'\r\n{HOSTNAME}#"

                    # Always echo the command first (PTY behaviour that netmiko's
                    # global_cmd_verify relies on), then the response.
                    # For setup commands (empty response) just send the prompt.
                    if response == "":
                        channel.sendall(f"{cmd}\r\n{HOSTNAME}#".encode())
                    else:
                        channel.sendall(f"{cmd}\r\n{response}\r\n".encode())

            except (OSError, EOFError):
                break
    except Exception as e:
        print(f"Error handling client {address}: {e}")
    finally:
        try:
            channel.close()
        except Exception:
            pass
        transport.close()


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", SSH_PORT))
    sock.listen(5)
    print(f"[Mock Cisco {HOSTNAME}] SSH server listening on port {SSH_PORT}")

    def shutdown(sig, frame):
        print(f"\n[Mock Cisco {HOSTNAME}] Shutting down...")
        sock.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        try:
            client_socket, address = sock.accept()
            print(f"[Mock Cisco {HOSTNAME}] Connection from {address}")
            t = threading.Thread(target=handle_client, args=(client_socket, address))
            t.daemon = True
            t.start()
        except OSError:
            break


if __name__ == "__main__":
    main()
