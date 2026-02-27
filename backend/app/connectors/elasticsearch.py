"""Elasticsearch connector (SSH).

Syncs the Elasticsearch cluster node and its indices into the Neo4j graph
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


class ElasticsearchConnector(BaseConnector):
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
        cluster_name = hostname

        # --- Device (cluster health) ---
        try:
            health_out = await asyncio.to_thread(
                self._run_ssh, "curl localhost:9200/_cluster/health",
            )
            # Strip trailing prompt (e.g. "hostname$ ")
            health_text = re.split(r'\n\S+\$\s*$', health_out.strip())[0].strip()
            try:
                info = json.loads(health_text)
                cluster_name = info.get("cluster_name", hostname)
            except json.JSONDecodeError:
                pass

            device_id = f"ES-{_safe_id(cluster_name)}"
            device_dn = display_name.device(
                display_name.VENDOR_ELASTICSEARCH, display_name.FUNCTION_SEARCH, cluster_name,
            )
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "search_engine", "vendor": "elasticsearch",
                "hostname": hostname, "cluster_name": cluster_name,
                "criticality": "medium", "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "elasticsearch", **result.to_dict()}

        # --- Indices ---
        try:
            idx_out = await asyncio.to_thread(
                self._run_ssh, "curl localhost:9200/_cat/indices",
            )
            for line in idx_out.splitlines():
                line = line.strip()
                if not line or "$" in line and line.endswith("$ "):
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue
                health = parts[0]
                idx_name = parts[2]
                if idx_name.startswith("."):
                    continue
                docs_count = parts[5] if len(parts) > 5 else "0"
                idx_id = f"INDEX-{_safe_id(cluster_name)}-{_safe_id(idx_name)}"
                try:
                    await neo4j_client.merge_node("Index", idx_id, {
                        "id": idx_id, "name": idx_name,
                        "health": health,
                        "docs_count": docs_count,
                        "display_name": f"Index {idx_name}  (Elasticsearch \u2014 {cluster_name})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_INDEX", "Index", idx_id)
                    result.record_success("indices")
                except Exception as e:
                    result.record_failure("indices", str(e))
        except Exception as e:
            result.record_failure("indices", str(e))

        result.finalise()
        return {"vendor": "elasticsearch", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "elasticsearch", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "elasticsearch", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "elasticsearch", "applied": False, "error": "not implemented"}
