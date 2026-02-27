"""Redis application connector (SSH / redis-cli).

Syncs the Redis cache/data-store server and its replica topology into the
Neo4j graph.
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


class RedisAppConnector(BaseConnector):
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
            return {"vendor": "redis", **result.to_dict()}

        device_id = f"REDIS-{_safe_id(hostname)}"
        device_dn = display_name.device(display_name.VENDOR_REDIS, display_name.FUNCTION_CACHE, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "cache", "vendor": "redis",
                "hostname": hostname, "criticality": "medium",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # Replicas
        try:
            info_out = await asyncio.to_thread(self._run_ssh, "redis-cli info replication 2>/dev/null")
            for line in info_out.splitlines():
                m = re.match(r"^slave\d+:ip=([^,]+),port=(\d+)", line)
                if not m:
                    continue
                slave_ip = m.group(1)
                slave_port = m.group(2)
                repl_id = f"REDIS-REPLICA-{_safe_id(hostname)}-{_safe_id(slave_ip)}-{slave_port}"
                try:
                    await neo4j_client.merge_node("Replica", repl_id, {
                        "id": repl_id, "address": f"{slave_ip}:{slave_port}",
                        "display_name": f"Replica {slave_ip}:{slave_port}  (Redis \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_REPLICA", "Replica", repl_id)
                    result.record_success("replicas")
                except Exception as e:
                    result.record_failure("replicas", str(e))
        except Exception as e:
            result.record_failure("replicas", str(e))

        result.finalise()
        return {"vendor": "redis", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "redis", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "redis", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "redis", "applied": False, "error": "not implemented"}
