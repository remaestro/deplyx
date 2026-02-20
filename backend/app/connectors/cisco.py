"""Cisco connector via NAPALM.

Uses NAPALM to sync switch config (interfaces, VLANs, ARP table) into the Neo4j graph.
"""

import time
from typing import Any
import re

from app.connectors.base import BaseConnector
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CiscoConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.driver_type = config.get("driver_type") or config.get("driver", "ios")  # ios | nxos | iosxr
        self.retry_count = int(config.get("retry_count", 3))

    def _candidate_drivers(self) -> list[str]:
        primary = str(self.driver_type or "ios").strip().lower()
        candidates: list[str]
        if primary == "nxos":
            candidates = ["nxos", "nxos_ssh"]
        elif primary == "ios":
            candidates = ["ios", "iosxr"]
        else:
            candidates = [primary]
        seen: list[str] = []
        for item in candidates:
            if item and item not in seen:
                seen.append(item)
        return seen

    def _optional_args(self) -> dict[str, Any]:
        return {
            "secret": self.password,
            "conn_timeout": 20,
            "timeout": 60,
            "auth_timeout": 20,
            "banner_timeout": 20,
            "fast_cli": False,
        }

    def _get_driver(self, driver_type: str):
        from napalm import get_network_driver
        driver_cls = get_network_driver(driver_type)
        return driver_cls(
            hostname=self.host,
            username=self.username,
            password=self.password,
            optional_args=self._optional_args(),
        )

    def _open_driver_with_retry(self):
        last_exc: Exception | None = None
        retries = max(1, self.retry_count)
        for attempt in range(1, retries + 1):
            for candidate in self._candidate_drivers():
                driver = None
                try:
                    driver = self._get_driver(candidate)
                    driver.open()
                    if candidate != self.driver_type:
                        logger.warning("Cisco connector fallback driver in use for %s: %s -> %s", self.host, self.driver_type, candidate)
                    return driver
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "Cisco connect attempt %s/%s failed for %s using driver=%s: %s",
                        attempt,
                        retries,
                        self.host,
                        candidate,
                        exc,
                    )
                    try:
                        if driver is not None:
                            driver.close()
                    except Exception:
                        pass
            if attempt < retries:
                time.sleep(min(attempt, 3))

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Unable to connect to {self.host}")

    async def _sync_via_paramiko(self) -> dict[str, int]:
        import paramiko

        synced: dict[str, int] = {"devices": 0, "interfaces": 0, "vlans": 0}

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            self.host,
            username=self.username,
            password=self.password,
            timeout=10,
            banner_timeout=20,
            auth_timeout=20,
        )

        try:
            def run_cmd(cmd: str) -> str:
                stdin, stdout, stderr = client.exec_command(cmd)
                out = stdout.read().decode(errors="ignore")
                if out.strip():
                    return out
                return stderr.read().decode(errors="ignore")

            version = run_cmd("show version")
            hostname_match = re.search(r"\b([A-Za-z0-9._-]+)[#:$]", version)
            hostname = hostname_match.group(1) if hostname_match else self.host
            serial_match = re.search(r"(?:Processor board ID|Serial Number|serial)\s*[:#]?\s*([A-Za-z0-9-]+)", version, re.IGNORECASE)
            serial = serial_match.group(1) if serial_match else self.host.replace(".", "-")

            device_id = f"CISCO-{serial}"
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id,
                "type": "switch",
                "vendor": "cisco",
                "hostname": hostname,
                "criticality": "medium",
                "model": "",
                "os_version": "",
                "ingestion_mode": "paramiko-fallback",
            })
            synced["devices"] = 1

            interfaces_raw = run_cmd("show interfaces")
            seen_ifaces: set[str] = set()
            for line in interfaces_raw.splitlines():
                m = re.match(r"^([A-Za-z]+[A-Za-z0-9/.-]*)\s+is\s+", line.strip())
                if not m:
                    continue
                iface_name = m.group(1)
                if iface_name in seen_ifaces:
                    continue
                seen_ifaces.add(iface_name)
                iface_id = f"IF-CISCO-{hostname}-{iface_name}"
                await neo4j_client.merge_node("Interface", iface_id, {
                    "id": iface_id,
                    "name": iface_name,
                    "speed": "",
                    "status": "up" if " is up" in line.lower() else "down",
                    "device_id": device_id,
                })
                await neo4j_client.create_relationship("Device", device_id, "HAS_INTERFACE", "Interface", iface_id)
                synced["interfaces"] += 1

            vlan_raw = run_cmd("show vlan")
            for line in vlan_raw.splitlines():
                m = re.match(r"^(\d+)\s+([A-Za-z0-9_.-]+)", line.strip())
                if not m:
                    continue
                vlan_id_str = m.group(1)
                vlan_name = m.group(2)
                vlan_id = f"VLAN-{vlan_id_str}"
                await neo4j_client.merge_node("VLAN", vlan_id, {
                    "id": vlan_id,
                    "vlan_id": int(vlan_id_str),
                    "name": vlan_name,
                })
                await neo4j_client.create_relationship("Device", device_id, "HOSTS", "VLAN", vlan_id)
                synced["vlans"] += 1

            return synced
        finally:
            client.close()

    async def sync(self) -> dict[str, Any]:
        synced: dict[str, int] = {"devices": 0, "interfaces": 0, "vlans": 0}
        driver = None

        try:
            driver = self._open_driver_with_retry()

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

        except Exception as e:
            logger.error("Cisco sync error: %s", e)
            try:
                fallback_synced = await self._sync_via_paramiko()
                return {
                    "vendor": "cisco",
                    "status": "synced",
                    "synced": fallback_synced,
                    "mode": "paramiko-fallback",
                    "warning": str(e),
                }
            except Exception as fallback_exc:
                return {
                    "vendor": "cisco",
                    "status": "error",
                    "error": f"{e} | fallback_failed: {fallback_exc}",
                    "synced": synced,
                }
        finally:
            try:
                if driver is not None:
                    driver.close()
            except Exception:
                pass

        return {"vendor": "cisco", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        driver = None
        try:
            driver = self._open_driver_with_retry()
            # Load candidate config (merge)
            driver.load_merge_candidate(config=payload.get("config", ""))
            diff = driver.compare_config()
            driver.discard_config()
            return {"vendor": "cisco", "valid": True, "diff": diff}
        except Exception as e:
            return {"vendor": "cisco", "valid": False, "error": str(e)}
        finally:
            try:
                if driver is not None:
                    driver.close()
            except Exception:
                pass

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Same as validate — NAPALM's compare_config is the simulation
        return await self.validate_change(payload)

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        driver = None
        try:
            driver = self._open_driver_with_retry()
            driver.load_merge_candidate(config=payload.get("config", ""))
            diff = driver.compare_config()
            driver.commit_config()
            return {"vendor": "cisco", "applied": True, "diff": diff}
        except Exception as e:
            return {"vendor": "cisco", "applied": False, "error": str(e)}
        finally:
            try:
                if driver is not None:
                    driver.close()
            except Exception:
                pass
