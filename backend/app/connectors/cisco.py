"""Cisco connector via NAPALM.

Uses NAPALM to sync switch config (interfaces, VLANs, ARP table) into the Neo4j graph.
"""

from typing import Any

from app.connectors.base import BaseConnector
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CiscoConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.driver_type = config.get("driver_type", "ios")  # ios | nxos | iosxr

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

            # Device facts
            facts = driver.get_facts()
            hostname = facts.get("hostname", self.host)
            serial = facts.get("serial_number", "unknown")
            device_id = f"CISCO-{serial}"

            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "switch", "vendor": "cisco",
                "hostname": hostname, "criticality": "medium",
                "model": facts.get("model", ""),
                "os_version": facts.get("os_version", ""),
            })
            synced["devices"] = 1

            # Interfaces
            interfaces = driver.get_interfaces()
            for name, details in interfaces.items():
                iface_id = f"IF-CISCO-{hostname}-{name}"
                await neo4j_client.merge_node("Interface", iface_id, {
                    "id": iface_id, "name": name,
                    "speed": str(details.get("speed", "")),
                    "status": "up" if details.get("is_up") else "down",
                    "device_id": device_id,
                })
                await neo4j_client.create_relationship("Device", device_id, "HAS_INTERFACE", "Interface", iface_id)
                synced["interfaces"] += 1

            # VLANs (if supported)
            try:
                vlans = driver.get_vlans()
                for vlan_id_str, vlan_info in vlans.items():
                    vlan_id = f"VLAN-{vlan_id_str}"
                    await neo4j_client.merge_node("VLAN", vlan_id, {
                        "id": vlan_id, "vlan_id": int(vlan_id_str),
                        "name": vlan_info.get("name", ""),
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HOSTS", "VLAN", vlan_id)
                    synced["vlans"] += 1
            except Exception:
                logger.debug("VLAN retrieval not supported on %s", self.driver_type)

            # IPs from interface IPs
            try:
                iface_ips = driver.get_interfaces_ip()
                for iface_name, ip_data in iface_ips.items():
                    for version in ("ipv4", "ipv6"):
                        for addr, info in ip_data.get(version, {}).items():
                            ip_id = f"IP-{addr}"
                            await neo4j_client.merge_node("IP", ip_id, {
                                "id": ip_id, "address": addr,
                                "subnet": f"{addr}/{info.get('prefix_length', 24)}",
                                "version": 4 if version == "ipv4" else 6,
                            })
                            iface_node_id = f"IF-CISCO-{hostname}-{iface_name}"
                            await neo4j_client.create_relationship("Interface", iface_node_id, "HAS_IP", "IP", ip_id)
            except Exception:
                logger.debug("Interface IP retrieval failed for %s", self.host)

            driver.close()

        except Exception as e:
            logger.error("Cisco sync error: %s", e)
            return {"vendor": "cisco", "status": "error", "error": str(e), "synced": synced}

        return {"vendor": "cisco", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            driver = self._get_driver()
            driver.open()
            # Load candidate config (merge)
            driver.load_merge_candidate(config=payload.get("config", ""))
            diff = driver.compare_config()
            driver.discard_config()
            driver.close()
            return {"vendor": "cisco", "valid": True, "diff": diff}
        except Exception as e:
            return {"vendor": "cisco", "valid": False, "error": str(e)}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Same as validate — NAPALM's compare_config is the simulation
        return await self.validate_change(payload)

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            driver = self._get_driver()
            driver.open()
            driver.load_merge_candidate(config=payload.get("config", ""))
            diff = driver.compare_config()
            driver.commit_config()
            driver.close()
            return {"vendor": "cisco", "applied": True, "diff": diff}
        except Exception as e:
            return {"vendor": "cisco", "applied": False, "error": str(e)}
