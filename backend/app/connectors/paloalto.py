"""Palo Alto Networks PAN-OS connector.

Uses the PAN-OS REST/XML API to:
  - sync(): fetch devices, interfaces, security rules → upsert into Neo4j
  - validate_change(): dry-run a rule change against the candidate config
  - simulate_change(): commit validation (dry-run)
  - apply_change(): push config change
"""

from typing import Any
import re

import requests
import urllib3

from app.connectors.base import BaseConnector
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = get_logger(__name__)


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-") or "unknown"


class PaloAltoConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.api_key = config.get("api_key", "")
        self.verify_ssl = config.get("verify_ssl", False)
        self.base_url = f"https://{self.host}/restapi/v10.1"

    def _headers(self) -> dict[str, str]:
        return {"X-PAN-KEY": self.api_key, "Content-Type": "application/json"}

    async def sync(self) -> dict[str, Any]:
        """Fetch system info, interfaces, and security rules from PAN-OS and upsert into Neo4j."""
        synced: dict[str, int] = {"devices": 0, "interfaces": 0, "rules": 0}
        device_id: str | None = None

        try:
            # Fetch system info
            resp = requests.get(
                f"https://{self.host}/api/?type=op&cmd=<show><system><info></info></system></show>&key={self.api_key}",
                verify=self.verify_ssl, timeout=30,
            )
            if resp.ok:
                # Parse XML response to extract hostname
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.text)
                hostname_el = root.find(".//hostname")
                hostname = hostname_el.text if hostname_el is not None else self.host
                serial_el = root.find(".//serial")
                serial = serial_el.text if serial_el is not None else "unknown"

                device_id = f"PA-{serial}"
                await neo4j_client.merge_node("Device", device_id, {
                    "id": device_id, "type": "firewall", "vendor": "paloalto",
                    "hostname": hostname, "criticality": "critical",
                })
                synced["devices"] = 1

            # Fetch interfaces
            iface_resp = requests.get(
                f"https://{self.host}/api/?type=op&cmd=<show><interface>all</interface></show>&key={self.api_key}",
                verify=self.verify_ssl, timeout=30,
            )
            if iface_resp.ok:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(iface_resp.text)
                for entry in root.findall(".//entry"):
                    name = entry.findtext("name", "")
                    if name:
                        iface_id = f"IF-PA-{name}"
                        await neo4j_client.merge_node("Interface", iface_id, {
                            "id": iface_id, "name": name, "status": "up",
                        })
                        if device_id:
                            await neo4j_client.create_relationship("Device", device_id, "HAS_INTERFACE", "Interface", iface_id)
                        synced["interfaces"] += 1

            # Fetch security rules
            rules_resp = requests.get(
                f"{self.base_url}/Policies/SecurityRules?location=vsys&vsys=vsys1",
                headers=self._headers(), verify=self.verify_ssl, timeout=30,
            )
            if rules_resp.ok:
                data = rules_resp.json()
                entries = data.get("result", {}).get("entry", [])
                if isinstance(entries, dict):
                    entries = [entries]
                for entry in entries:
                    rule_name = entry.get("@name", "")
                    rule_id = f"PA-RULE-{rule_name}"
                    src = entry.get("source", {}).get("member", ["any"])
                    dst = entry.get("destination", {}).get("member", ["any"])
                    action = entry.get("action", "allow")

                    await neo4j_client.merge_node("Rule", rule_id, {
                        "id": rule_id, "name": rule_name,
                        "source": src[0] if isinstance(src, list) else str(src),
                        "destination": dst[0] if isinstance(dst, list) else str(dst),
                        "action": action if isinstance(action, str) else "allow",
                    })

                    if not device_id:
                        device_id = f"PA-HOST-{_safe_id(self.host)}"
                        await neo4j_client.merge_node("Device", device_id, {
                            "id": device_id,
                            "type": "firewall",
                            "vendor": "paloalto",
                            "hostname": self.host,
                            "criticality": "critical",
                        })
                        synced["devices"] = max(1, synced["devices"])

                    await neo4j_client.create_relationship("Device", device_id, "HAS_RULE", "Rule", rule_id)

                    destinations = dst if isinstance(dst, list) else [str(dst)]
                    for dst_name in destinations:
                        dst_value = str(dst_name)
                        if dst_value.lower() in {"any", "all"}:
                            continue
                        app_id = f"APP-{_safe_id(dst_value)}"
                        await neo4j_client.merge_node("Application", app_id, {
                            "id": app_id,
                            "name": dst_value,
                            "label": dst_value,
                            "criticality": "medium",
                        })
                        await neo4j_client.create_relationship("Rule", rule_id, "PROTECTS", "Application", app_id)

                    synced["rules"] += 1

        except requests.RequestException as e:
            logger.error("PaloAlto sync error: %s", e)
            return {"vendor": "paloalto", "status": "error", "error": str(e), "synced": synced}

        return {"vendor": "paloalto", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate a proposed rule change against the PAN-OS candidate config."""
        try:
            resp = requests.post(
                f"{self.base_url}/Policies/SecurityRules?location=vsys&vsys=vsys1&name={payload.get('rule_name', '')}",
                headers=self._headers(), json={"entry": payload.get("rule_config", {})},
                verify=self.verify_ssl, timeout=30,
            )
            return {"vendor": "paloalto", "valid": resp.ok, "status_code": resp.status_code, "response": resp.text[:500]}
        except requests.RequestException as e:
            return {"vendor": "paloalto", "valid": False, "error": str(e)}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Commit validation (dry-run) on PAN-OS."""
        try:
            resp = requests.get(
                f"https://{self.host}/api/?type=op&cmd=<validate><full></full></validate>&key={self.api_key}",
                verify=self.verify_ssl, timeout=60,
            )
            return {"vendor": "paloalto", "simulation": "ok" if resp.ok else "failed", "response": resp.text[:500]}
        except requests.RequestException as e:
            return {"vendor": "paloalto", "simulation": "error", "error": str(e)}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push and commit a config change on PAN-OS."""
        try:
            # First set the config
            set_resp = requests.put(
                f"{self.base_url}/Policies/SecurityRules?location=vsys&vsys=vsys1&name={payload.get('rule_name', '')}",
                headers=self._headers(), json={"entry": payload.get("rule_config", {})},
                verify=self.verify_ssl, timeout=30,
            )
            if not set_resp.ok:
                return {"vendor": "paloalto", "applied": False, "error": f"Set failed: {set_resp.status_code}"}

            # Then commit
            commit_resp = requests.get(
                f"https://{self.host}/api/?type=commit&cmd=<commit></commit>&key={self.api_key}",
                verify=self.verify_ssl, timeout=120,
            )
            return {
                "vendor": "paloalto", "applied": commit_resp.ok,
                "commit_status": "ok" if commit_resp.ok else "failed",
            }
        except requests.RequestException as e:
            return {"vendor": "paloalto", "applied": False, "error": str(e)}
