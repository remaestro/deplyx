"""Nginx application connector (SSH).

Syncs the Nginx reverse-proxy / load-balancer server and its virtual hosts
into the Neo4j graph.
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


class NginxAppConnector(BaseConnector):
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
            return {"vendor": "nginx", **result.to_dict()}

        device_id = f"NGINX-{_safe_id(hostname)}"
        device_dn = display_name.device(display_name.VENDOR_NGINX, display_name.FUNCTION_PROXY, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "reverse_proxy", "vendor": "nginx",
                "hostname": hostname, "criticality": "medium",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # Virtual hosts
        try:
            vhost_out = await asyncio.to_thread(self._run_ssh, "nginx -T 2>/dev/null | grep -E 'server_name\\s'")
            seen: set[str] = set()
            for line in vhost_out.splitlines():
                m = re.search(r"server_name\s+([^;]+);", line)
                if not m:
                    continue
                names = m.group(1).strip().split()
                for name in names:
                    name = name.strip()
                    if not name or name == "_" or name in seen:
                        continue
                    seen.add(name)
                    vhost_id = f"VHOST-{_safe_id(hostname)}-{_safe_id(name)}"
                    try:
                        await neo4j_client.merge_node("VirtualHost", vhost_id, {
                            "id": vhost_id, "server_name": name,
                            "display_name": f"VHost {name}  (Nginx \u2014 {hostname})",
                        })
                        await neo4j_client.create_relationship("Device", device_id, "HAS_VHOST", "VirtualHost", vhost_id)
                        result.record_success("vhosts")
                    except Exception as e:
                        result.record_failure("vhosts", str(e))
        except Exception as e:
            result.record_failure("vhosts", str(e))

        result.finalise()
        return {"vendor": "nginx", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "nginx", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "nginx", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "nginx", "applied": False, "error": "not implemented"}
