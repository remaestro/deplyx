"""Juniper connector via NAPALM (junos driver)."""

from typing import Any

from app.connectors.base import BaseConnector
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


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
            optional_args={"secret": self.password},
        )

    async def sync(self) -> dict[str, Any]:
        synced: dict[str, int] = {"devices": 0, "interfaces": 0, "vlans": 0}

        try:
            driver = self._get_driver()
            driver.open()

            facts = driver.get_facts()
            hostname = facts.get("hostname", self.host)
            serial = facts.get("serial_number", "unknown")
            device_id = f"JUNIPER-{serial}"

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
                },
            )
            synced["devices"] = 1

            interfaces = driver.get_interfaces()
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
                    },
                )
                await neo4j_client.create_relationship("Device", device_id, "HAS_INTERFACE", "Interface", iface_id)
                synced["interfaces"] += 1

            try:
                vlans = driver.get_vlans()
                for vlan_id_str, vlan_info in vlans.items():
                    vlan_id = f"VLAN-{vlan_id_str}"
                    await neo4j_client.merge_node(
                        "VLAN",
                        vlan_id,
                        {
                            "id": vlan_id,
                            "vlan_id": int(vlan_id_str),
                            "name": vlan_info.get("name", ""),
                        },
                    )
                    await neo4j_client.create_relationship("Device", device_id, "HOSTS", "VLAN", vlan_id)
                    synced["vlans"] += 1
            except Exception:
                logger.debug("Juniper VLAN retrieval failed for %s", self.host)

            driver.close()
        except Exception as e:
            logger.error("Juniper sync error: %s", e)
            return {"vendor": "juniper", "status": "error", "error": str(e), "synced": synced}

        return {"vendor": "juniper", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            driver = self._get_driver()
            driver.open()
            driver.load_merge_candidate(config=payload.get("config", ""))
            diff = driver.compare_config()
            driver.discard_config()
            driver.close()
            return {"vendor": "juniper", "valid": True, "diff": diff}
        except Exception as e:
            return {"vendor": "juniper", "valid": False, "error": str(e)}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.validate_change(payload)

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            driver = self._get_driver()
            driver.open()
            driver.load_merge_candidate(config=payload.get("config", ""))
            diff = driver.compare_config()
            driver.commit_config()
            driver.close()
            return {"vendor": "juniper", "applied": True, "diff": diff}
        except Exception as e:
            return {"vendor": "juniper", "applied": False, "error": str(e)}
