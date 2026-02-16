"""Check Point connector.

Syncs gateways and access-layer rules into the graph.
"""

from typing import Any

import requests

from app.connectors.base import BaseConnector
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CheckPointConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.domain = config.get("domain", "")
        self.verify_ssl = config.get("verify_ssl", False)
        self.base_url = f"https://{self.host}/web_api"

    def _login(self) -> str:
        resp = requests.post(
            f"{self.base_url}/login",
            json={"user": self.username, "password": self.password, "domain": self.domain} if self.domain else {"user": self.username, "password": self.password},
            verify=self.verify_ssl,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("sid", "")

    async def sync(self) -> dict[str, Any]:
        synced: dict[str, int] = {"gateways": 0, "rules": 0}
        try:
            sid = self._login()
            headers = {"X-chkp-sid": sid, "Content-Type": "application/json"}

            gateways_resp = requests.post(
                f"{self.base_url}/show-simple-gateways",
                json={"limit": 200, "offset": 0},
                headers=headers,
                verify=self.verify_ssl,
                timeout=30,
            )
            gateways_resp.raise_for_status()
            gateways = gateways_resp.json().get("objects", [])

            for gw in gateways:
                gateway_id = f"CP-{gw.get('uid', gw.get('name', 'unknown'))}"
                await neo4j_client.merge_node(
                    "Device",
                    gateway_id,
                    {
                        "id": gateway_id,
                        "type": "firewall",
                        "vendor": "checkpoint",
                        "hostname": gw.get("name", gateway_id),
                        "criticality": "critical",
                    },
                )
                synced["gateways"] += 1

            rules_resp = requests.post(
                f"{self.base_url}/show-access-rulebase",
                json={"name": "Network", "details-level": "standard", "limit": 500, "offset": 0},
                headers=headers,
                verify=self.verify_ssl,
                timeout=45,
            )
            rules_resp.raise_for_status()
            rules = rules_resp.json().get("rulebase", [])

            for idx, rule in enumerate(rules):
                if rule.get("type") != "access-rule":
                    continue
                rule_id = f"CP-RULE-{rule.get('uid', idx)}"
                await neo4j_client.merge_node(
                    "Rule",
                    rule_id,
                    {
                        "id": rule_id,
                        "name": rule.get("name", rule_id),
                        "source": "any",
                        "destination": "any",
                        "port": "any",
                        "protocol": "any",
                        "action": (rule.get("action", {}) or {}).get("name", "allow"),
                    },
                )
                synced["rules"] += 1

            requests.post(f"{self.base_url}/logout", headers=headers, verify=self.verify_ssl, timeout=15)

        except requests.RequestException as e:
            logger.error("CheckPoint sync error: %s", e)
            return {"vendor": "checkpoint", "status": "error", "error": str(e), "synced": synced}

        return {"vendor": "checkpoint", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            sid = self._login()
            headers = {"X-chkp-sid": sid, "Content-Type": "application/json"}
            requests.post(f"{self.base_url}/show-access-rulebase", json={"name": payload.get("policy_package", "Network"), "limit": 1}, headers=headers, verify=self.verify_ssl, timeout=20).raise_for_status()
            requests.post(f"{self.base_url}/logout", headers=headers, verify=self.verify_ssl, timeout=15)
            return {"vendor": "checkpoint", "valid": True}
        except requests.RequestException as e:
            return {"vendor": "checkpoint", "valid": False, "error": str(e)}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.validate_change(payload)

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            sid = self._login()
            headers = {"X-chkp-sid": sid, "Content-Type": "application/json"}
            requests.post(
                f"{self.base_url}/set-access-rule",
                json=payload,
                headers=headers,
                verify=self.verify_ssl,
                timeout=30,
            ).raise_for_status()
            publish_resp = requests.post(f"{self.base_url}/publish", headers=headers, verify=self.verify_ssl, timeout=30)
            publish_ok = publish_resp.ok
            requests.post(f"{self.base_url}/logout", headers=headers, verify=self.verify_ssl, timeout=15)
            return {"vendor": "checkpoint", "applied": publish_ok}
        except requests.RequestException as e:
            return {"vendor": "checkpoint", "applied": False, "error": str(e)}
