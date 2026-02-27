"""StrongSwan VPN connector (SSH / vici).

Syncs VPN gateway device and IPsec tunnels into the Neo4j graph.
"""

import asyncio
import re
from typing import Any

from app.connectors.base import BaseConnector, SyncResult
from app.connectors import display_name
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_") or "unknown"


class StrongSwanVPNConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")

    def _run_ssh(self, command: str) -> str:
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(self.host, username=self.username, password=self.password, timeout=10)
        try:
            _stdin, stdout, _stderr = client.exec_command(command, timeout=30)
            stdout.channel.settimeout(30)
            return stdout.read().decode(errors="ignore")
        finally:
            client.close()

    async def sync(self) -> dict[str, Any]:
        result = SyncResult()
        hostname = self.host

        try:
            hostname_out = (await asyncio.to_thread(self._run_ssh, "hostname")).strip()
            if hostname_out:
                hostname = hostname_out
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "strongswan", **result.to_dict()}

        device_id = f"VPN-{_safe_id(hostname)}"
        device_dn = display_name.device(display_name.VENDOR_STRONGSWAN, display_name.FUNCTION_VPN, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "vpn_gateway", "vendor": "strongswan",
                "hostname": hostname, "criticality": "high",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # IPsec tunnels
        try:
            sa_out = await asyncio.to_thread(self._run_ssh, "ipsec statusall")
            conn_names: list[str] = []
            for line in sa_out.splitlines():
                m = re.match(r"^\s*(\S+)\[?\d*\]?:\s+IKEv[12]", line)
                if m:
                    conn_names.append(m.group(1))
                    continue
                m2 = re.match(r"^Connections:\s*$", line)
                if m2:
                    continue
                m3 = re.match(r"^\s+(\S+):\s+IKEv[12]", line)
                if m3:
                    conn_names.append(m3.group(1))

            for conn_name in set(conn_names):
                tunnel_id = f"VPN-TUNNEL-{_safe_id(hostname)}-{_safe_id(conn_name)}"
                try:
                    await neo4j_client.merge_node("VPNTunnel", tunnel_id, {
                        "id": tunnel_id, "name": conn_name,
                        "display_name": f"Tunnel {conn_name}  (StrongSwan \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_VPN_TUNNEL", "VPNTunnel", tunnel_id)
                    result.record_success("tunnels")
                except Exception as e:
                    result.record_failure("tunnels", str(e))
        except Exception as e:
            result.record_failure("tunnels", str(e))

        result.finalise()
        return {"vendor": "strongswan", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "strongswan", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "strongswan", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "strongswan", "applied": False, "error": "not implemented"}
