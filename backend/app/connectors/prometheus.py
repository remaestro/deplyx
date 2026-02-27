"""Prometheus connector (SSH).

Syncs the Prometheus monitoring server and its scrape targets into the Neo4j
graph by running diagnostic commands over SSH.
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


class PrometheusConnector(BaseConnector):
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

        # --- Device ---
        try:
            status_out = await asyncio.to_thread(
                self._run_ssh, "systemctl status prometheus",
            )
            # Just verify we got output — device is reachable
            device_id = f"PROM-{_safe_id(hostname)}"
            device_dn = display_name.device(
                display_name.VENDOR_PROMETHEUS, display_name.FUNCTION_METRICS, hostname,
            )
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "metrics", "vendor": "prometheus",
                "hostname": hostname, "criticality": "low",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "prometheus", **result.to_dict()}

        # --- Scrape targets ---
        try:
            targets_out = await asyncio.to_thread(
                self._run_ssh, "curl localhost:9090/api/v1/targets",
            )
            # Strip trailing prompt and parse JSON
            targets_text = re.split(r'\n\S+\$\s*$', targets_out.strip())[0].strip()
            try:
                payload = json.loads(targets_text)
            except json.JSONDecodeError:
                result.record_failure("targets", "Could not parse targets JSON")
                result.finalise()
                return {"vendor": "prometheus", **result.to_dict()}

            data = payload.get("data", {})
            active_targets = data.get("activeTargets", [])
            seen: set[str] = set()
            for t in active_targets:
                labels = t.get("labels", {})
                job = labels.get("job", "unknown")
                instance = labels.get("instance", "unknown")
                key = f"{job}-{instance}"
                if key in seen:
                    continue
                seen.add(key)
                target_id = f"TARGET-{_safe_id(hostname)}-{_safe_id(key)}"
                try:
                    await neo4j_client.merge_node("ScrapeTarget", target_id, {
                        "id": target_id, "job": job, "instance": instance,
                        "health": t.get("health", "unknown"),
                        "display_name": f"Target {job}/{instance}  (Prometheus \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship(
                        "Device", device_id, "HAS_SCRAPE_TARGET", "ScrapeTarget", target_id,
                    )
                    result.record_success("targets")
                except Exception as e:
                    result.record_failure("targets", str(e))
        except Exception as e:
            result.record_failure("targets", str(e))

        result.finalise()
        return {"vendor": "prometheus", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "prometheus", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "prometheus", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "prometheus", "applied": False, "error": "not implemented"}
