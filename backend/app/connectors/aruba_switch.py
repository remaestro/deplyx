"""Aruba Switch connector (SSH).

Syncs device, interfaces, and VLANs into the Neo4j graph.
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


class ArubaSwitchConnector(BaseConnector):
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
            _stdin, stdout, stderr = client.exec_command(command, timeout=30)
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
                m = re.search(r"System Name\s*:\s*(\S+)", line, re.IGNORECASE)
                if m:
                    hostname = m.group(1)
                m2 = re.search(r"Serial\s*(?:Number)?\s*:\s*(\S+)", line, re.IGNORECASE)
                if m2:
                    serial = _safe_id(m2.group(1))
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "aruba-switch", **result.to_dict()}

        device_id = f"ARUBA-SW-{serial}"
        device_dn = display_name.device(display_name.VENDOR_ARUBA, display_name.FUNCTION_SWITCH, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "switch", "vendor": "aruba",
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
                m = re.match(r"^\s*(\S+)\s+is\s+(up|down)", line.strip(), re.IGNORECASE)
                if not m:
                    continue
                ifname = m.group(1)
                status = m.group(2).lower()
                iface_id = f"IF-ARUBA-SW-{hostname}-{ifname}"
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

        # VLANs
        try:
            vlan_out = await asyncio.to_thread(self._run_ssh, "show vlans")
            for line in vlan_out.splitlines():
                m = re.match(r"^\s*(\d+)\s+(\S+)", line.strip())
                if not m:
                    continue
                vid = m.group(1)
                vlan_id = f"VLAN-{vid}"
                try:
                    await neo4j_client.merge_node("VLAN", vlan_id, {
                        "id": vlan_id, "vlan_id": int(vid),
                        "display_name": display_name.vlan(vid),
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HOSTS", "VLAN", vlan_id)
                    result.record_success("vlans")
                except Exception as e:
                    result.record_failure("vlans", str(e))
        except Exception as e:
            result.record_failure("vlans", str(e))

        result.finalise()
        return {"vendor": "aruba-switch", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "aruba-switch", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "aruba-switch", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "aruba-switch", "applied": False, "error": "not implemented"}
