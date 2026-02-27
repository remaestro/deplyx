"""PostgreSQL application connector (SSH / psql).

Syncs the PostgreSQL database server and its databases into the Neo4j graph.
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


class PostgresAppConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.pg_user = config.get("pg_user", "postgres")

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
            return {"vendor": "postgres", **result.to_dict()}

        device_id = f"PG-{_safe_id(hostname)}"
        device_dn = display_name.device(display_name.VENDOR_POSTGRES, display_name.FUNCTION_DATABASE, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "database", "vendor": "postgres",
                "hostname": hostname, "criticality": "high",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # Databases
        try:
            db_out = await asyncio.to_thread(
                self._run_ssh,
                f"sudo -u {self.pg_user} psql -Atc \"SELECT datname FROM pg_database WHERE datistemplate = false;\" 2>/dev/null"
            )
            for line in db_out.strip().splitlines():
                db_name = line.strip()
                if not db_name:
                    continue
                db_id = f"DB-{_safe_id(hostname)}-{_safe_id(db_name)}"
                try:
                    await neo4j_client.merge_node("Database", db_id, {
                        "id": db_id, "name": db_name,
                        "display_name": f"DB {db_name}  (PostgreSQL \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HOSTS", "Database", db_id)
                    result.record_success("databases")
                except Exception as e:
                    result.record_failure("databases", str(e))
        except Exception as e:
            result.record_failure("databases", str(e))

        # Replicas
        try:
            repl_out = await asyncio.to_thread(
                self._run_ssh,
                f"sudo -u {self.pg_user} psql -Atc \"SELECT client_addr FROM pg_stat_replication;\" 2>/dev/null"
            )
            for line in repl_out.strip().splitlines():
                addr = line.strip()
                if not addr:
                    continue
                repl_id = f"REPLICA-{_safe_id(hostname)}-{_safe_id(addr)}"
                try:
                    await neo4j_client.merge_node("Replica", repl_id, {
                        "id": repl_id, "address": addr,
                        "display_name": f"Replica {addr}  (PostgreSQL \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_REPLICA", "Replica", repl_id)
                    result.record_success("replicas")
                except Exception as e:
                    result.record_failure("replicas", str(e))
        except Exception as e:
            result.record_failure("replicas", str(e))

        result.finalise()
        return {"vendor": "postgres", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "postgres", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "postgres", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "postgres", "applied": False, "error": "not implemented"}
