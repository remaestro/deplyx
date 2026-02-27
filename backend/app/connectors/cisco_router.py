"""Cisco Router connector (SSH).

Syncs device, interfaces, routes, and BGP peers into the Neo4j graph.
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


class CiscoRouterConnector(BaseConnector):
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
        serial = _safe_id(self.host)

        try:
            version_out = await asyncio.to_thread(self._run_ssh, "show version")
            for line in version_out.splitlines():
                hm = re.search(r"(\S+)\s+uptime", line, re.IGNORECASE)
                if hm:
                    hostname = hm.group(1)
                sm = re.search(r"Processor board ID\s+(\S+)", line, re.IGNORECASE)
                if sm:
                    serial = _safe_id(sm.group(1))
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "cisco-router", **result.to_dict()}

        device_id = f"ROUTER-{serial}"
        device_dn = display_name.device(display_name.VENDOR_CISCO, display_name.FUNCTION_ROUTER, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "router", "vendor": "cisco",
                "hostname": hostname, "criticality": "high",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # Interfaces
        try:
            iface_out = await asyncio.to_thread(self._run_ssh, "show interfaces")
            for line in iface_out.splitlines():
                m = re.match(r"^(\S+)\s+is\s+(up|down)", line.strip(), re.IGNORECASE)
                if not m:
                    continue
                ifname = m.group(1)
                status = m.group(2).lower()
                iface_id = f"IF-ROUTER-{hostname}-{ifname}"
                try:
                    await neo4j_client.merge_node("Interface", iface_id, {
                        "id": iface_id, "name": ifname, "status": status,
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
                network = rm.group(1)
                network_safe = _safe_id(network)
                route_id = f"ROUTE-{hostname}-{network_safe}"
                try:
                    await neo4j_client.merge_node("Route", route_id, {
                        "id": route_id, "network": network,
                        "display_name": f"Route {network}  ({hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_ROUTE", "Route", route_id)
                    result.record_success("routes")
                except Exception as e:
                    result.record_failure("routes", str(e))
        except Exception as e:
            result.record_failure("routes", str(e))

        # BGP peers
        try:
            bgp_out = await asyncio.to_thread(self._run_ssh, "show ip bgp summary")
            asn = ""
            for line in bgp_out.splitlines():
                am = re.search(r"local AS number\s+(\d+)", line, re.IGNORECASE)
                if am:
                    asn = am.group(1)
                bm = re.match(r"^(\d+\.\d+\.\d+\.\d+)\s+", line.strip())
                if bm and asn:
                    neighbor = _safe_id(bm.group(1))
                    bgp_id = f"BGP-{asn}-{neighbor}"
                    try:
                        await neo4j_client.merge_node("BGPPeer", bgp_id, {
                            "id": bgp_id, "asn": asn, "neighbor": bm.group(1),
                            "display_name": f"BGP Peer {bm.group(1)} (AS {asn})",
                        })
                        await neo4j_client.create_relationship("Device", device_id, "HAS_BGP_PEER", "BGPPeer", bgp_id)
                        result.record_success("bgp_peers")
                    except Exception as e:
                        result.record_failure("bgp_peers", str(e))
        except Exception as e:
            result.record_failure("bgp_peers", str(e))

        result.finalise()
        return {"vendor": "cisco-router", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-router", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-router", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-router", "applied": False, "error": "not implemented"}
