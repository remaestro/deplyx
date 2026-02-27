"""Grafana connector (SSH).

Syncs the Grafana monitoring server and its datasources into the Neo4j graph
by running diagnostic commands over SSH.
"""

import asyncio
import json
import re
from typing import Any

from app.connectors.base import BaseConnector, SyncResult
from app.connectors import display_name
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_") or "unknown"


class GrafanaConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.username = config.get("username", "admin")
        self.password = config.get("password", "admin")

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

        # --- Device (health check) ---
        try:
            health_out = await asyncio.to_thread(
                self._run_ssh, "curl localhost:3000/api/health",
            )
            # Parse JSON health — strip trailing prompt
            health_text = re.split(r'\n\S+\$\s*$', health_out.strip())[0].strip()
            version = "unknown"
            try:
                info = json.loads(health_text)
                version = info.get("version", "unknown")
            except json.JSONDecodeError:
                pass

            device_id = f"GRAFANA-{_safe_id(hostname)}"
            device_dn = display_name.device(
                display_name.VENDOR_GRAFANA, display_name.FUNCTION_MONITORING, hostname,
            )
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "monitoring", "vendor": "grafana",
                "hostname": hostname, "version": version,
                "criticality": "low", "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "grafana", **result.to_dict()}

        # --- Datasources ---
        try:
            ds_out = await asyncio.to_thread(
                self._run_ssh, "grafana-cli datasources list",
            )
            # Parse lines like: "  1. Prometheus   (default) - http://prometheus:9090 - [UID: prometheus-main]"
            for line in ds_out.splitlines():
                m = re.match(
                    r'\s*\d+\.\s+(\S+)\s+.*?-\s+(\S+)\s*-\s*\[UID:\s*(\S+)\]',
                    line,
                )
                if not m:
                    continue
                ds_name = m.group(1)
                ds_url = m.group(2)
                ds_uid = m.group(3)
                ds_id = f"DS-{_safe_id(hostname)}-{_safe_id(ds_name)}"
                try:
                    await neo4j_client.merge_node("DataSource", ds_id, {
                        "id": ds_id, "name": ds_name, "url": ds_url,
                        "uid": ds_uid,
                        "display_name": f"DS {ds_name}  (Grafana \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship(
                        "Device", device_id, "HAS_DATASOURCE", "DataSource", ds_id,
                    )
                    result.record_success("datasources")
                except Exception as e:
                    result.record_failure("datasources", str(e))
        except Exception as e:
            result.record_failure("datasources", str(e))

        result.finalise()
        return {"vendor": "grafana", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "grafana", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "grafana", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "grafana", "applied": False, "error": "not implemented"}
