"""Mock Juniper JunOS NETCONF server.

NAPALM junos driver uses PyEZ (junos-eznc) which opens a NETCONF 1.0 session
over SSH (subsystem "netconf"). This server:
  - Completes the NETCONF hello capability exchange
  - Handles the RPCs PyEZ/NAPALM actually sends (get-software-information,
    get-chassis-information, get-system-information, get-interface-information,
    get-vlan-information, get-config, edit-config, commit, discard-changes,
    lock, unlock, close-session)
  - Returns Junos-shaped XML with realistic data
  - Uses ]]>]]> end-of-message framing (NETCONF 1.0)

All non-NETCONF connections are rejected; this is a NETCONF-only device.
"""

import os
import threading
import signal
import sys
import socket
import re

import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)

HOSTNAME = os.getenv("JUNIPER_HOSTNAME", "SW-DC2-CORE")
SERIAL   = os.getenv("JUNIPER_SERIAL",   "JN1234567890")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Juniper123!")

# ---------------------------------------------------------------------------
# NETCONF framing helpers
# ---------------------------------------------------------------------------
EOM = b"]]>]]>"


def _frame(xml: str) -> bytes:
    """Wrap an XML reply in NETCONF 1.0 end-of-message framing."""
    return xml.encode() + b"\n" + EOM + b"\n"


def _rpc_reply(message_id: str, inner_xml: str) -> bytes:
    return _frame(
        f'<rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"'
        f' xmlns:junos="http://xml.juniper.net/junos/22.4R0/junos"'
        f' message-id="{message_id}">'
        f"{inner_xml}"
        f"</rpc-reply>"
    )


def _ok_reply(message_id: str) -> bytes:
    return _rpc_reply(message_id, "<ok/>")


# ---------------------------------------------------------------------------
# Junos XML data blobs — shapes that PyEZ parsers expect
# ---------------------------------------------------------------------------

def _software_info_xml() -> str:
    return f"""<software-information>
  <host-name>{HOSTNAME}</host-name>
  <product-model>EX4300-48T</product-model>
  <product-name>EX4300-48T</product-name>
  <junos-version>22.4R2-S1</junos-version>
  <package-information>
    <name>os</name>
    <comment>JUNOS EX  Software Suite [22.4R2-S1]</comment>
  </package-information>
</software-information>"""


def _chassis_info_xml() -> str:
    return f"""<chassis-inventory>
  <chassis>
    <name>Chassis</name>
    <serial-number>{SERIAL}</serial-number>
    <description>EX4300-48T</description>
  </chassis>
</chassis-inventory>"""


def _system_info_xml() -> str:
    return f"""<system-information>
  <host-name>{HOSTNAME}</host-name>
  <hardware-model>EX4300-48T</hardware-model>
  <os-name>junos</os-name>
  <os-version>22.4R2-S1</os-version>
  <serial-number>{SERIAL}</serial-number>
</system-information>"""


def _interfaces_xml() -> str:
    ifaces = [
        ("ge-0/0/0", "up",   "up",   "1000mbps", "UPLINK-TO-FW-DC2", "00:05:86:00:01:00"),
        ("ge-0/0/1", "up",   "up",   "1000mbps", "SERVER-VLAN-110",  "00:05:86:00:01:01"),
        ("ge-0/0/2", "up",   "up",   "1000mbps", "DMZ-VLAN-120",     "00:05:86:00:01:02"),
        ("ge-0/0/3", "up",   "down", "unspecified", "SPARE",          "00:05:86:00:01:03"),
        ("irb",      "up",   "up",   "unspecified", "IRB",            "00:05:86:00:01:10"),
        ("lo0",      "up",   "up",   "unspecified", "Loopback",       "00:00:00:00:00:00"),
    ]
    parts = []
    for name, admin, oper, speed, desc, mac in ifaces:
        parts.append(f"""<physical-interface>
  <name>{name}</name>
  <admin-status>{admin}</admin-status>
  <oper-status>{oper}</oper-status>
  <description>{desc}</description>
  <current-physical-address>{mac}</current-physical-address>
  <speed>{speed}</speed>
  <mtu>1514</mtu>
</physical-interface>""")
    return "<interface-information>" + "".join(parts) + "</interface-information>"


def _vlan_xml() -> str:
    # Structure expected by NAPALM junos_vlans_table_switch_l2ng:
    #   item: l2ng-l2ald-vlan-instance-group
    #   key:  l2ng-l2rtb-vlan-tag
    #   view: vlan_name=l2ng-l2rtb-vlan-name, interfaces=l2ng-l2rtb-vlan-member/...
    vlans = [
        ("SERVERS",    "110", "ge-0/0/1.0"),
        ("DMZ",        "120", "ge-0/0/2.0"),
        ("MANAGEMENT", "130", ""),
        ("DATABASE",   "140", ""),
        ("BACKUP",     "150", ""),
    ]
    parts = []
    for name, tag, iface in vlans:
        iface_xml = (
            f"<l2ng-l2rtb-vlan-member>"
            f"<l2ng-l2rtb-vlan-member-interface>{iface}</l2ng-l2rtb-vlan-member-interface>"
            f"</l2ng-l2rtb-vlan-member>"
        ) if iface else ""
        parts.append(
            f"<l2ng-l2ald-vlan-instance-group>"
            f"<l2ng-l2rtb-vlan-name>{name}</l2ng-l2rtb-vlan-name>"
            f"<l2ng-l2rtb-vlan-tag>{tag}</l2ng-l2rtb-vlan-tag>"
            f"{iface_xml}"
            f"</l2ng-l2ald-vlan-instance-group>"
        )
    return "<l2ng-l2ald-vlan-instance-information>" + "".join(parts) + "</l2ng-l2ald-vlan-instance-information>"


# Running config returned by get-config
_RUNNING_CONFIG = f"""<configuration>
  <system>
    <host-name>{HOSTNAME}</host-name>
    <domain-name>deplyx.lab</domain-name>
    <services>
      <ssh/>
      <netconf><ssh/></netconf>
    </services>
  </system>
  <interfaces>
    <interface>
      <name>ge-0/0/0</name>
      <description>UPLINK-TO-FW-DC2</description>
      <unit><name>0</name><family><inet><address><name>172.16.0.2/24</name></address></inet></family></unit>
    </interface>
    <interface>
      <name>ge-0/0/1</name>
      <description>SERVER-VLAN-110</description>
      <unit><name>0</name><family><ethernet-switching><vlan><members>SERVERS</members></vlan></ethernet-switching></family></unit>
    </interface>
    <interface>
      <name>ge-0/0/2</name>
      <description>DMZ-VLAN-120</description>
      <unit><name>0</name><family><ethernet-switching><vlan><members>DMZ</members></vlan></ethernet-switching></family></unit>
    </interface>
    <interface>
      <name>ge-0/0/3</name>
      <description>SPARE</description>
      <disable/>
    </interface>
    <interface>
      <name>irb</name>
      <unit><name>0</name><family><inet><address><name>172.16.99.1/24</name></address></inet></family></unit>
    </interface>
    <interface>
      <name>lo0</name>
      <unit><name>0</name><family><inet><address><name>172.16.255.1/32</name></address></inet></family></unit>
    </interface>
  </interfaces>
  <vlans>
    <vlan><name>SERVERS</name><vlan-id>110</vlan-id></vlan>
    <vlan><name>DMZ</name><vlan-id>120</vlan-id></vlan>
    <vlan><name>MANAGEMENT</name><vlan-id>130</vlan-id></vlan>
    <vlan><name>DATABASE</name><vlan-id>140</vlan-id></vlan>
    <vlan><name>BACKUP</name><vlan-id>150</vlan-id></vlan>
  </vlans>
  <routing-options>
    <static>
      <route><name>0.0.0.0/0</name><next-hop>172.16.0.1</next-hop></route>
    </static>
  </routing-options>
</configuration>"""

# Candidate config (mutable per-session — we keep it global for simplicity)
_candidate_config: dict = {}


# ---------------------------------------------------------------------------
# NETCONF session handler
# ---------------------------------------------------------------------------

def _extract_message_id(xml: str) -> str:
    m = re.search(r'message-id=["\']([^"\']+)["\']', xml)
    return m.group(1) if m else "1"


def _handle_rpc(xml: str) -> bytes:
    """Dispatch a single RPC request and return the framed reply bytes."""
    message_id = _extract_message_id(xml)
    xml_lower = xml.lower()

    # close-session / lock / unlock — always OK
    if "<close-session" in xml_lower or "<lock" in xml_lower or "<unlock" in xml_lower:
        return _ok_reply(message_id)

    # discard-changes
    if "<discard-changes" in xml_lower:
        _candidate_config.clear()
        return _ok_reply(message_id)

    # commit
    if "<commit" in xml_lower:
        _candidate_config.clear()
        return _ok_reply(message_id)

    # edit-config — accept anything, store candidate
    if "<edit-config" in xml_lower:
        _candidate_config["pending"] = xml
        return _ok_reply(message_id)

    # get-config — return running or candidate
    if "<get-config" in xml_lower:
        inner = f"<data>{_RUNNING_CONFIG}</data>"
        return _rpc_reply(message_id, inner)

    # get-software-information
    if "get-software-information" in xml_lower:
        return _rpc_reply(message_id, _software_info_xml())

    # get-chassis-information / get-chassis-inventory
    if "get-chassis-information" in xml_lower or "get-chassis-inventory" in xml_lower:
        return _rpc_reply(message_id, _chassis_info_xml())

    # get-system-information (used by some PyEZ versions)
    if "get-system-information" in xml_lower:
        return _rpc_reply(message_id, _system_info_xml())

    # get-interface-information  (NAPALM get_interfaces / get_interfaces_ip)
    if "get-interface-information" in xml_lower:
        return _rpc_reply(message_id, _interfaces_xml())

    # get-vlan-information / l2ald VLAN table (NAPALM get_vlans)
    if ("get-vlan-information" in xml_lower
            or "get-l2ng-l2ald-vlan" in xml_lower
            or "get-l2ng-l2rtb-mac-ip-table" in xml_lower):
        return _rpc_reply(message_id, _vlan_xml())

    # Ethernet switching table — PyEZ ethernet_mac_table.py checks the response tag
    # to determine switch_style.  Return l2ng-l2ald-rtb-macdb so it resolves to VLAN_L2NG.
    if "get-ethernet-switching-table-information" in xml_lower:
        return _rpc_reply(
            message_id,
            "<l2ng-l2ald-rtb-macdb><l2ng-mac-entry-count>0</l2ng-mac-entry-count></l2ng-l2ald-rtb-macdb>",
        )

    # <command> RPCs (e.g. "show bridge mac-table count")
    if "<command>" in xml_lower:
        # Extract the actual CLI command text
        cmd_m = re.search(r"<command[^>]*>(.*?)</command>", xml, re.IGNORECASE | re.DOTALL)
        cmd_text = (cmd_m.group(1).strip().lower() if cmd_m else "")

        if "show version" in cmd_text:
            # _get_swver() in NAPALM tries cli("show version ...") first and falls
            # back to get-software-information on exception.  Return an error here
            # so the except-clause triggers and we get called via the proper RPC.
            return _rpc_reply(
                message_id,
                "<rpc-error>"
                "<error-type>application</error-type>"
                "<error-tag>unknown-element</error-tag>"
                "<error-severity>error</error-severity>"
                "<error-message>CLI command not supported in NETCONF context</error-message>"
                "</rpc-error>",
            )

        # All other <command> RPCs (bridge mac-table, etc.) — return empty output
        return _rpc_reply(message_id, "<output></output>")

    # Generic <get> with filter — return running config data
    if "<get" in xml_lower:
        inner = f"<data>{_RUNNING_CONFIG}</data>"
        return _rpc_reply(message_id, inner)

    # Unknown RPC — return <ok/> so callers treat it as a no-op instead of raising.
    # (Real Junos returns <ok/> for RPCs it doesn't support in the current context.)
    return _ok_reply(message_id)


def handle_netconf_session(channel: paramiko.Channel) -> None:
    """Run a full NETCONF 1.0 session on the given paramiko channel."""

    # Send our <hello> first
    server_hello = _frame(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">'
        "<capabilities>"
        "<capability>urn:ietf:params:xml:ns:netconf:base:1.0</capability>"
        "<capability>urn:ietf:params:xml:ns:netconf:capability:writable-running:1.0</capability>"
        "<capability>urn:ietf:params:xml:ns:netconf:capability:candidate:1.0</capability>"
        "<capability>urn:ietf:params:xml:ns:netconf:capability:confirmed-commit:1.0</capability>"
        "<capability>urn:ietf:params:xml:ns:netconf:capability:rollback-on-error:1.0</capability>"
        "<capability>urn:ietf:params:xml:ns:netconf:capability:validate:1.0</capability>"
        "<capability>urn:ietf:params:xml:ns:netconf:capability:url:1.0</capability>"
        "<capability>http://xml.juniper.net/netconf/junos/1.0</capability>"
        f"</capabilities><session-id>1</session-id>"
        "</hello>"
    )
    channel.sendall(server_hello)

    buf = b""
    while True:
        try:
            chunk = channel.recv(8192)
            if not chunk:
                break
            buf += chunk

            # Split on ]]>]]> end-of-message marker
            while EOM in buf:
                msg_bytes, buf = buf.split(EOM, 1)
                msg = msg_bytes.decode("utf-8", errors="replace").strip()
                if not msg:
                    continue

                # Skip the client hello — no reply needed.
                # ncclient may send <hello> or <nc:hello> (with namespace prefix),
                # so we detect by the presence of <capabilities> which only appears
                # in hello messages, never in RPCs.
                if "<capabilities" in msg.lower() or "hello" in msg.lower():
                    continue

                reply = _handle_rpc(msg)
                channel.sendall(reply)

                # Close after <close-session>
                if "<close-session" in msg.lower():
                    return

        except (OSError, EOFError):
            break


# ---------------------------------------------------------------------------
# SSH server — accepts only the 'netconf' subsystem
# ---------------------------------------------------------------------------

class _NetconfSSHServer(paramiko.ServerInterface):
    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL if username == SSH_USER and password == SSH_PASS else paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        # Accept any key — authentication via password is sufficient for the lab
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_channel_subsystem_request(self, channel, name):
        # NAPALM junos uses "netconf" subsystem
        return name == "netconf"

    def check_channel_shell_request(self, channel):
        # Reject plain shell — this is NETCONF-only
        return False

    def check_channel_exec_request(self, channel, command):
        return False


def _handle_connection(client_socket: socket.socket, address) -> None:
    transport = paramiko.Transport(client_socket)
    transport.add_server_key(HOST_KEY)
    server_iface = _NetconfSSHServer()

    try:
        transport.start_server(server=server_iface)
    except paramiko.SSHException as exc:
        print(f"[Juniper] SSH negotiation failed from {address}: {exc}")
        client_socket.close()
        return

    channel = transport.accept(30)
    if channel is None:
        print(f"[Juniper] No channel opened from {address}")
        transport.close()
        return

    try:
        handle_netconf_session(channel)
    except Exception as exc:
        print(f"[Juniper] Session error from {address}: {exc}")
    finally:
        try:
            channel.close()
        except Exception:
            pass
        transport.close()


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", SSH_PORT))
    sock.listen(10)
    print(f"[Mock Juniper NETCONF] {HOSTNAME} listening on port {SSH_PORT}")

    def _shutdown(sig, frame):
        print(f"\n[Mock Juniper] Shutting down...")
        sock.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        try:
            client_socket, address = sock.accept()
            print(f"[Juniper] Connection from {address}")
            t = threading.Thread(target=_handle_connection, args=(client_socket, address))
            t.daemon = True
            t.start()
        except OSError:
            break


if __name__ == "__main__":
    main()
