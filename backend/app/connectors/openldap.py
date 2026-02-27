"""OpenLDAP connector (LDAP bind).

Syncs the LDAP directory server and its top-level OUs/entries into the Neo4j
graph via an SSH-based ldapsearch call.
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


class OpenLDAPConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.bind_dn = config.get("bind_dn", "cn=admin,dc=example,dc=org")
        self.bind_pw = config.get("bind_pw", "")
        self.base_dn = config.get("base_dn", "dc=example,dc=org")
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
            return {"vendor": "openldap", **result.to_dict()}

        device_id = f"LDAP-{_safe_id(hostname)}"
        device_dn = display_name.device(display_name.VENDOR_OPENLDAP, display_name.FUNCTION_DIRECTORY, hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "directory", "vendor": "openldap",
                "hostname": hostname, "criticality": "medium",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # Top-level OUs
        try:
            search_cmd = (
                f"ldapsearch -x -H ldap://localhost -D '{self.bind_dn}' "
                f"-w '{self.bind_pw}' -b '{self.base_dn}' "
                f"-s one '(objectClass=organizationalUnit)' ou 2>/dev/null"
            )
            out = await asyncio.to_thread(self._run_ssh, search_cmd)
            for line in out.splitlines():
                m = re.match(r"^ou:\s*(.+)$", line)
                if not m:
                    continue
                ou = m.group(1).strip()
                ou_id = f"OU-{_safe_id(hostname)}-{_safe_id(ou)}"
                try:
                    await neo4j_client.merge_node("OrganizationalUnit", ou_id, {
                        "id": ou_id, "name": ou,
                        "display_name": f"OU {ou}  (OpenLDAP \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "PART_OF", "OrganizationalUnit", ou_id)
                    result.record_success("ous")
                except Exception as e:
                    result.record_failure("ous", str(e))
        except Exception as e:
            result.record_failure("ous", str(e))

        result.finalise()
        return {"vendor": "openldap", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "openldap", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "openldap", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "openldap", "applied": False, "error": "not implemented"}
