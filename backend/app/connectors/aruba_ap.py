"""Aruba AP connector (SSH).

Syncs Aruba access points, radios, and WLANs into the Neo4j graph.
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


class ArubaAPConnector(BaseConnector):
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
            sys_out = await asyncio.to_thread(self._run_ssh, "show system")
            for line in sys_out.splitlines():
                hm = re.search(r"Hostname\s*:\s*(\S+)", line, re.IGNORECASE)
                if hm:
                    hostname = hm.group(1)
                sm = re.search(r"Serial\s*:\s*(\S+)", line, re.IGNORECASE)
                if sm:
                    serial = _safe_id(sm.group(1))
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "aruba-ap", **result.to_dict()}

        device_id = f"ARUBA-AP-{serial}"
        device_dn = display_name.device(display_name.VENDOR_ARUBA, display_name.FUNCTION_AP, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "access_point", "vendor": "aruba",
                "hostname": hostname, "criticality": "low",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # Radios
        try:
            radio_out = await asyncio.to_thread(self._run_ssh, "show radio status")
            radio_idx = 0
            for line in radio_out.splitlines():
                rm = re.match(r"^\s*(radio|wlan)\s*(\d+)", line, re.IGNORECASE)
                if not rm:
                    continue
                radio_idx += 1
                radio_id = f"RADIO-{hostname}-{radio_idx}"
                try:
                    await neo4j_client.merge_node("Radio", radio_id, {
                        "id": radio_id, "radio_index": radio_idx,
                        "display_name": f"Radio {radio_idx}  (Aruba AP \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_RADIO", "Radio", radio_id)
                    result.record_success("radios")
                except Exception as e:
                    result.record_failure("radios", str(e))
        except Exception as e:
            result.record_failure("radios", str(e))

        # WLANs
        try:
            wlan_out = await asyncio.to_thread(self._run_ssh, "show wlan summary")
            for line in wlan_out.splitlines():
                wm = re.match(r"^\s*(\S+)\s+(\S+)", line.strip())
                if not wm or wm.group(1).lower() in {"profile", "name", "---"}:
                    continue
                ssid = wm.group(1)
                wlan_id = f"WLAN-{hostname}-{_safe_id(ssid)}"
                try:
                    await neo4j_client.merge_node("WLAN", wlan_id, {
                        "id": wlan_id, "ssid": ssid,
                        "display_name": f"WLAN {ssid}  (Aruba AP \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "SERVES_WLAN", "WLAN", wlan_id)
                    result.record_success("wlans")
                except Exception as e:
                    result.record_failure("wlans", str(e))
        except Exception as e:
            result.record_failure("wlans", str(e))

        result.finalise()
        return {"vendor": "aruba-ap", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "aruba-ap", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "aruba-ap", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "aruba-ap", "applied": False, "error": "not implemented"}
