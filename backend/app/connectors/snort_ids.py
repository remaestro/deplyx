"""Snort IDS connector (SSH / Unix socket).

Syncs Snort IDS sensor and its active rule sets into the Neo4j graph.
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


class SnortIDSConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.rules_path = config.get("rules_path", "/etc/snort/rules")

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
            return {"vendor": "snort", **result.to_dict()}

        device_id = f"IDS-{_safe_id(hostname)}"
        device_dn = display_name.device(display_name.VENDOR_SNORT, display_name.FUNCTION_IDS, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "ids", "vendor": "snort",
                "hostname": hostname, "criticality": "high",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # Rules
        try:
            rules_out = await asyncio.to_thread(self._run_ssh, f"ls {self.rules_path}/*.rules 2>/dev/null || echo ''")
            for line in rules_out.strip().splitlines():
                line = line.strip()
                if not line or line.endswith("No such file"):
                    continue
                rule_file = line.rsplit("/", 1)[-1].replace(".rules", "")
                rule_id_str = _safe_id(rule_file)
                rule_node_id = f"RULE-{_safe_id(hostname)}-{rule_id_str}"
                try:
                    dn = display_name.rule(rule_id_str, device_dn)
                    await neo4j_client.merge_node("Rule", rule_node_id, {
                        "id": rule_node_id, "name": rule_file,
                        "display_name": dn,
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_RULE", "Rule", rule_node_id)
                    result.record_success("rules")
                except Exception as e:
                    result.record_failure("rules", str(e))
        except Exception as e:
            result.record_failure("rules", str(e))

        result.finalise()
        return {"vendor": "snort", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "snort", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "snort", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "snort", "applied": False, "error": "not implemented"}
