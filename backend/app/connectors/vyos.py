"""VyOS Router connector (SSH).

Syncs device, interfaces, routes, and VPN tunnels into the Neo4j graph.
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


class VyOSConnector(BaseConnector):
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
        hostname = _safe_id(self.host)

        try:
            version_out = await asyncio.to_thread(self._run_ssh, "show version")
            for line in version_out.splitlines():
                hm = re.search(r"host-name\s+(\S+)", line, re.IGNORECASE)
                if hm:
                    hostname = hm.group(1)
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "vyos", **result.to_dict()}

        device_id = f"VYOS-{hostname}"
        device_dn = display_name.device(display_name.VENDOR_VYOS, display_name.FUNCTION_ROUTER, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "router", "vendor": "vyos",
                "hostname": hostname, "criticality": "medium",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # Interfaces
        try:
            iface_out = await asyncio.to_thread(self._run_ssh, "show interfaces")
            for line in iface_out.splitlines():
                m = re.match(r"^(\S+)\s+", line.strip())
                if not m or m.group(1).lower() in {"interface", "---", ""}:
                    continue
                ifname = m.group(1)
                iface_id = f"IF-VYOS-{hostname}-{ifname}"
                try:
                    await neo4j_client.merge_node("Interface", iface_id, {
                        "id": iface_id, "name": ifname,
                        "display_name": display_name.interface(ifname, device_dn),
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_INTERFACE", "Interface", iface_id)
                    result.record_success("interfaces")
                except Exception as e:
                    result.record_failure("interfaces", str(e))
        except Exception as e:
            result.record_failure("interfaces", str(e))

        # Routes
        try:
            route_out = await asyncio.to_thread(self._run_ssh, "show ip route")
            for line in route_out.splitlines():
                rm = re.search(r"(\d+\.\d+\.\d+\.\d+/\d+)", line)
                if not rm:
                    continue
                prefix = rm.group(1)
                prefix_safe = _safe_id(prefix)
                route_id = f"ROUTE-{hostname}-{prefix_safe}"
                try:
                    await neo4j_client.merge_node("Route", route_id, {
                        "id": route_id, "prefix": prefix,
                        "display_name": f"Route {prefix}  ({hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_ROUTE", "Route", route_id)
                    result.record_success("routes")
                except Exception as e:
                    result.record_failure("routes", str(e))
        except Exception as e:
            result.record_failure("routes", str(e))

        # VPN tunnels
        try:
            vpn_out = await asyncio.to_thread(self._run_ssh, "show vpn ipsec sa")
            for line in vpn_out.splitlines():
                pm = re.search(r"peer\s+(\d+\.\d+\.\d+\.\d+)", line, re.IGNORECASE)
                if not pm:
                    continue
                peer = pm.group(1)
                peer_safe = _safe_id(peer)
                vpn_id = f"VPN-{hostname}-{peer_safe}"
                try:
                    await neo4j_client.merge_node("VPNTunnel", vpn_id, {
                        "id": vpn_id, "peer": peer,
                        "display_name": f"VPN Tunnel to {peer}  ({hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_VPN_TUNNEL", "VPNTunnel", vpn_id)
                    result.record_success("vpn_tunnels")
                except Exception as e:
                    result.record_failure("vpn_tunnels", str(e))
        except Exception as e:
            result.record_failure("vpn_tunnels", str(e))

        result.finalise()
        return {"vendor": "vyos", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "vyos", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "vyos", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "vyos", "applied": False, "error": "not implemented"}
