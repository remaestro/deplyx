"""Cisco WLC connector (SSH).

Syncs wireless controller, WLANs, and access points into the Neo4j graph.
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


class CiscoWLCConnector(BaseConnector):
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
            version_out = await asyncio.to_thread(self._run_ssh, "show sysinfo")
            for line in version_out.splitlines():
                hm = re.search(r"System Name\s*\.+\s*(\S+)", line, re.IGNORECASE)
                if hm:
                    hostname = hm.group(1)
                sm = re.search(r"Serial Number\s*\.+\s*(\S+)", line, re.IGNORECASE)
                if sm:
                    serial = _safe_id(sm.group(1))
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "cisco-wlc", **result.to_dict()}

        device_id = f"WLC-{serial}"
        device_dn = display_name.device(display_name.VENDOR_CISCO, display_name.FUNCTION_WLC, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "wlc", "vendor": "cisco",
                "hostname": hostname, "criticality": "high",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # WLANs
        try:
            wlan_out = await asyncio.to_thread(self._run_ssh, "show wlan summary")
            for line in wlan_out.splitlines():
                wm = re.match(r"^\s*(\d+)\s+(\S+)", line.strip())
                if not wm:
                    continue
                wlan_id = wm.group(1)
                ssid = wm.group(2)
                wlan_node_id = f"WLAN-{hostname}-{wlan_id}"
                try:
                    await neo4j_client.merge_node("WLAN", wlan_node_id, {
                        "id": wlan_node_id, "wlan_id": wlan_id, "ssid": ssid,
                        "display_name": f"WLAN {ssid}  (Cisco WLC \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_WLAN", "WLAN", wlan_node_id)
                    result.record_success("wlans")
                except Exception as e:
                    result.record_failure("wlans", str(e))
        except Exception as e:
            result.record_failure("wlans", str(e))

        # Access Points
        try:
            ap_out = await asyncio.to_thread(self._run_ssh, "show ap summary")
            for line in ap_out.splitlines():
                am = re.match(r"^\s*(\S+)\s+", line.strip())
                if not am or am.group(1).lower() in {"ap", "name", "---", "number"}:
                    continue
                ap_name = am.group(1)
                ap_name_safe = _safe_id(ap_name)
                ap_id = f"AP-{hostname}-{ap_name_safe}"
                try:
                    await neo4j_client.merge_node("AccessPoint", ap_id, {
                        "id": ap_id, "name": ap_name,
                        "display_name": f"AP {ap_name}  (Cisco WLC \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_AP", "AccessPoint", ap_id)
                    result.record_success("access_points")
                except Exception as e:
                    result.record_failure("access_points", str(e))
        except Exception as e:
            result.record_failure("access_points", str(e))

        result.finalise()
        return {"vendor": "cisco-wlc", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-wlc", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-wlc", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-wlc", "applied": False, "error": "not implemented"}
