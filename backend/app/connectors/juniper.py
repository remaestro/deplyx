"""Juniper connector via NAPALM (junos driver)."""

import asyncio
import os
from typing import Any
import re

from app.connectors.base import BaseConnector
from app.connectors import display_name
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)

JUNIPER_CONN_TIMEOUT = int(os.environ.get("JUNIPER_CONN_TIMEOUT", "10"))
JUNIPER_COMMAND_TIMEOUT = int(os.environ.get("JUNIPER_COMMAND_TIMEOUT", "20"))


class JuniperConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.driver_type = "junos"

    def _get_driver(self):
        from napalm import get_network_driver

        driver_cls = get_network_driver(self.driver_type)
        return driver_cls(
            hostname=self.host,
            username=self.username,
            password=self.password,
            optional_args={
                "secret": self.password,
                "conn_timeout": JUNIPER_CONN_TIMEOUT,
                "timeout": JUNIPER_COMMAND_TIMEOUT,
            },
        )

    @staticmethod
    def _clean_identifier(value: str | None) -> str:
        token = str(value or "").strip()
        token = re.sub(r"\s+", "-", token)
        token = re.sub(r"[^A-Za-z0-9_.:-]", "-", token)
        token = re.sub(r"-+", "-", token).strip("-")
        return token

    def _device_id(self, serial: str | None, hostname: str | None) -> str:
        serial_token = self._clean_identifier(serial)
        if serial_token and serial_token.lower() not in {"unknown", "n/a", "na", "none", "null"}:
            return f"JUNIPER-{serial_token}"
        host_token = self._clean_identifier(hostname) or self._clean_identifier(self.host)
        return f"JUNIPER-HOST-{host_token or 'unresolved'}"

    async def sync(self) -> dict[str, Any]:
        synced: dict[str, int] = {"devices": 0, "interfaces": 0, "vlans": 0}

        try:
            driver = self._get_driver()
            await asyncio.to_thread(driver.open)

            facts = await asyncio.to_thread(driver.get_facts)
            hostname = facts.get("hostname", self.host)
            serial = facts.get("serial_number", "unknown")
            device_id = self._device_id(serial, hostname)
            device_dn = display_name.device(display_name.VENDOR_JUNIPER, display_name.FUNCTION_SWITCH, hostname)

            await neo4j_client.merge_node(
                "Device",
                device_id,
                {
                    "id": device_id,
                    "type": "switch",
                    "vendor": "juniper",
                    "hostname": hostname,
                    "criticality": "medium",
                    "model": facts.get("model", ""),
                    "os_version": facts.get("os_version", ""),
                    "display_name": device_dn,
                },
            )
            synced["devices"] = 1

            interfaces = await asyncio.to_thread(driver.get_interfaces)
            for name, details in interfaces.items():
                iface_id = f"IF-JUNIPER-{hostname}-{name}"
                await neo4j_client.merge_node(
                    "Interface",
                    iface_id,
                    {
                        "id": iface_id,
                        "name": name,
                        "speed": str(details.get("speed", "")),
                        "status": "up" if details.get("is_up") else "down",
                        "device_id": device_id,
                        "display_name": display_name.interface(name, device_dn),
                    },
                )
                await neo4j_client.create_relationship("Device", device_id, "HAS_INTERFACE", "Interface", iface_id)
                synced["interfaces"] += 1

            try:
                vlans = await asyncio.to_thread(driver.get_vlans)
                for vlan_id_str, vlan_info in vlans.items():
                    vlan_id = f"VLAN-{vlan_id_str}"
                    await neo4j_client.merge_node(
                        "VLAN",
                        vlan_id,
                        {
                            "id": vlan_id,
                            "vlan_id": int(vlan_id_str),
                            "name": vlan_info.get("name", ""),
                            "display_name": display_name.vlan(vlan_id_str),
                        },
                    )
                    await neo4j_client.create_relationship("Device", device_id, "HOSTS", "VLAN", vlan_id)
                    synced["vlans"] += 1
            except Exception:
                logger.debug("Juniper VLAN retrieval failed for %s", self.host)

            await asyncio.to_thread(driver.close)
        except Exception as e:
            logger.error("Juniper sync error: %s", e)
            return {"vendor": "juniper", "status": "error", "error": str(e), "synced": synced}

        return {"vendor": "juniper", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            driver = self._get_driver()
            await asyncio.to_thread(driver.open)
            await asyncio.to_thread(driver.load_merge_candidate, config=payload.get("config", ""))
            diff = await asyncio.to_thread(driver.compare_config)
            await asyncio.to_thread(driver.discard_config)
            await asyncio.to_thread(driver.close)
            return {"vendor": "juniper", "valid": True, "diff": diff}
        except Exception as e:
            return {"vendor": "juniper", "valid": False, "error": str(e)}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.validate_change(payload)

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            driver = self._get_driver()
            await asyncio.to_thread(driver.open)
            await asyncio.to_thread(driver.load_merge_candidate, config=payload.get("config", ""))
            diff = await asyncio.to_thread(driver.compare_config)
            await asyncio.to_thread(driver.commit_config)
            await asyncio.to_thread(driver.close)
            return {"vendor": "juniper", "applied": True, "diff": diff}
        except Exception as e:
            return {"vendor": "juniper", "applied": False, "error": str(e)}
