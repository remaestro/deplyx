"""Check Point connector.

Syncs gateways and access-layer rules into the graph.
"""

from typing import Any
import asyncio
import re

import requests

from app.connectors.base import BaseConnector
from app.connectors import display_name
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-") or "unknown"


def _names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return names


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
        policy_device_id = f"CP-MGMT-{_safe_id(self.host)}"
        sid: str | None = None
        try:
            sid = await asyncio.to_thread(self._login)
            headers = {"X-chkp-sid": sid, "Content-Type": "application/json"}

            await neo4j_client.merge_node(
                "Device",
                policy_device_id,
                {
                    "id": policy_device_id,
                    "type": "firewall",
                    "vendor": "checkpoint",
                    "hostname": self.host,
                    "criticality": "critical",
                    "display_name": display_name.device(
                        display_name.VENDOR_CHECK_POINT,
                        display_name.FUNCTION_FIREWALL,
                        self.host,
                    ),
                },
            )

            gateways_resp = await asyncio.to_thread(
                requests.post,
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
                        "display_name": display_name.device(
                            display_name.VENDOR_CHECK_POINT,
                            display_name.FUNCTION_FIREWALL,
                            gw.get("name", gateway_id),
                        ),
                    },
                )
                await neo4j_client.create_relationship("Device", policy_device_id, "CONNECTED_TO", "Device", gateway_id)
                synced["gateways"] += 1

            rules_resp = await asyncio.to_thread(
                requests.post,
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
                source_names = _names(rule.get("source"))
                destination_names = _names(rule.get("destination"))
                service_names = _names(rule.get("service"))
                source = source_names[0] if source_names else "any"
                destination = destination_names[0] if destination_names else "any"
                port = service_names[0] if service_names else "any"
                await neo4j_client.merge_node(
                    "Rule",
                    rule_id,
                    {
                        "id": rule_id,
                        "name": rule.get("name", rule_id),
                        "source": source,
                        "destination": destination,
                        "port": port,
                        "protocol": "any",
                        "action": (rule.get("action", {}) or {}).get("name", "allow"),
                        "display_name": display_name.rule(
                            rule.get("name", rule_id),
                            display_name.device(
                                display_name.VENDOR_CHECK_POINT,
                                display_name.FUNCTION_FIREWALL,
                                self.host,
                            ),
                        ),
                    },
                )
                await neo4j_client.create_relationship("Device", policy_device_id, "HAS_RULE", "Rule", rule_id)

                for dst_name in destination_names:
                    if dst_name.lower() in {"any", "all"}:
                        continue
                    app_id = f"APP-{_safe_id(dst_name)}"
                    await neo4j_client.merge_node(
                        "Application",
                        app_id,
                        {
                            "id": app_id,
                            "name": dst_name,
                            "label": dst_name,
                            "criticality": "medium",
                            "display_name": display_name.application(dst_name),
                        },
                    )
                    await neo4j_client.create_relationship("Rule", rule_id, "PROTECTS", "Application", app_id)

                synced["rules"] += 1

        except requests.RequestException as e:
            logger.error("CheckPoint sync error: %s", e)
            return {"vendor": "checkpoint", "status": "error", "error": str(e), "synced": synced}
        finally:
            if sid:
                try:
                    await asyncio.to_thread(
                        requests.post,
                        f"{self.base_url}/logout",
                        headers={"X-chkp-sid": sid, "Content-Type": "application/json"},
                        verify=self.verify_ssl,
                        timeout=15,
                    )
                except Exception as logout_exc:
                    logger.warning("Check Point logout failed: %s", logout_exc)

        return {"vendor": "checkpoint", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            sid = await asyncio.to_thread(self._login)
            headers = {"X-chkp-sid": sid, "Content-Type": "application/json"}
            resp = await asyncio.to_thread(requests.post, f"{self.base_url}/show-access-rulebase", json={"name": payload.get("policy_package", "Network"), "limit": 1}, headers=headers, verify=self.verify_ssl, timeout=20)
            resp.raise_for_status()
            await asyncio.to_thread(requests.post, f"{self.base_url}/logout", headers=headers, verify=self.verify_ssl, timeout=15)
            return {"vendor": "checkpoint", "valid": True}
        except requests.RequestException as e:
            return {"vendor": "checkpoint", "valid": False, "error": str(e)}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.validate_change(payload)

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            sid = await asyncio.to_thread(self._login)
            headers = {"X-chkp-sid": sid, "Content-Type": "application/json"}
            resp = await asyncio.to_thread(
                requests.post,
                f"{self.base_url}/set-access-rule",
                json=payload,
                headers=headers,
                verify=self.verify_ssl,
                timeout=30,
            )
            resp.raise_for_status()
            publish_resp = await asyncio.to_thread(requests.post, f"{self.base_url}/publish", headers=headers, verify=self.verify_ssl, timeout=30)
            publish_ok = publish_resp.ok
            await asyncio.to_thread(requests.post, f"{self.base_url}/logout", headers=headers, verify=self.verify_ssl, timeout=15)
            return {"vendor": "checkpoint", "applied": publish_ok}
        except requests.RequestException as e:
            return {"vendor": "checkpoint", "applied": False, "error": str(e)}
