"""Fortinet FortiOS connector.

Uses the FortiOS REST API to sync devices, interfaces, and firewall policies into Neo4j.
"""

from typing import Any

import requests
import urllib3

from app.connectors.base import BaseConnector
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = get_logger(__name__)


class FortinetConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.api_token = config.get("api_token", "")
        self.verify_ssl = config.get("verify_ssl", False)
        self.base_url = f"https://{self.host}/api/v2"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    async def sync(self) -> dict[str, Any]:
        synced: dict[str, int] = {"devices": 0, "interfaces": 0, "rules": 0}

        try:
            # System info
            resp = requests.get(
                f"{self.base_url}/monitor/system/status",
                headers=self._headers(), verify=self.verify_ssl, timeout=30,
            )
            if resp.ok:
                info = resp.json().get("results", {})
                hostname = info.get("hostname", self.host)
                serial = info.get("serial", "unknown")
                device_id = f"FG-{serial}"
                await neo4j_client.merge_node("Device", device_id, {
                    "id": device_id, "type": "firewall", "vendor": "fortinet",
                    "hostname": hostname, "criticality": "critical",
                })
                synced["devices"] = 1

            # Interfaces
            iface_resp = requests.get(
                f"{self.base_url}/cmdb/system/interface",
                headers=self._headers(), verify=self.verify_ssl, timeout=30,
            )
            if iface_resp.ok:
                for iface in iface_resp.json().get("results", []):
                    name = iface.get("name", "")
                    iface_id = f"IF-FG-{name}"
                    await neo4j_client.merge_node("Interface", iface_id, {
                        "id": iface_id, "name": name,
                        "status": iface.get("status", "up"),
                        "speed": iface.get("speed", ""),
                    })
                    synced["interfaces"] += 1

            # Firewall policies
            policy_resp = requests.get(
                f"{self.base_url}/cmdb/firewall/policy",
                headers=self._headers(), verify=self.verify_ssl, timeout=30,
            )
            if policy_resp.ok:
                for policy in policy_resp.json().get("results", []):
                    pid = policy.get("policyid", 0)
                    rule_id = f"FG-RULE-{pid}"
                    src = policy.get("srcaddr", [{}])[0].get("name", "any") if policy.get("srcaddr") else "any"
                    dst = policy.get("dstaddr", [{}])[0].get("name", "any") if policy.get("dstaddr") else "any"
                    action = "allow" if policy.get("action") == "accept" else "deny"

                    await neo4j_client.merge_node("Rule", rule_id, {
                        "id": rule_id, "name": policy.get("name", f"Policy {pid}"),
                        "source": src, "destination": dst, "action": action,
                    })
                    synced["rules"] += 1

        except requests.RequestException as e:
            logger.error("Fortinet sync error: %s", e)
            return {"vendor": "fortinet", "status": "error", "error": str(e), "synced": synced}

        return {"vendor": "fortinet", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = requests.get(
                f"{self.base_url}/cmdb/firewall/policy/{payload.get('policy_id', '')}",
                headers=self._headers(), verify=self.verify_ssl, timeout=30,
            )
            return {"vendor": "fortinet", "valid": resp.ok, "exists": resp.ok}
        except requests.RequestException as e:
            return {"vendor": "fortinet", "valid": False, "error": str(e)}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        # FortiOS doesn't have a native dry-run; we validate the policy exists
        return await self.validate_change(payload)

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = requests.put(
                f"{self.base_url}/cmdb/firewall/policy/{payload.get('policy_id', '')}",
                headers=self._headers(), json=payload.get("policy_config", {}),
                verify=self.verify_ssl, timeout=30,
            )
            return {"vendor": "fortinet", "applied": resp.ok, "status_code": resp.status_code}
        except requests.RequestException as e:
            return {"vendor": "fortinet", "applied": False, "error": str(e)}
