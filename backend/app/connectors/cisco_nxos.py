"""Cisco NX-OS connector (SSH).

Syncs device, interfaces, VLANs, BGP peers, and VRFs into the Neo4j graph.
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


class CiscoNXOSConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
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
        serial = _safe_id(self.host)

        try:
            version_out = await asyncio.to_thread(self._run_ssh, "show version")
            for line in version_out.splitlines():
                hm = re.search(r"Device name:\s*(\S+)", line, re.IGNORECASE)
                if hm:
                    hostname = hm.group(1)
                sm = re.search(r"Processor Board ID\s+(\S+)", line, re.IGNORECASE)
                if sm:
                    serial = _safe_id(sm.group(1))
        except Exception as e:
            result.record_failure("devices", str(e))
            result.finalise()
            return {"vendor": "cisco-nxos", **result.to_dict()}

        device_id = f"NXOS-{serial}"
        device_dn = display_name.device(display_name.VENDOR_CISCO, "NX-OS", hostname)
        try:
            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id, "type": "switch", "vendor": "cisco-nxos",
                "hostname": hostname, "criticality": "high",
                "display_name": device_dn,
            })
            result.record_success("devices")
        except Exception as e:
            result.record_failure("devices", str(e))

        # Interfaces
        try:
            iface_out = await asyncio.to_thread(self._run_ssh, "show interface")
            for line in iface_out.splitlines():
                m = re.match(r"^(\S+)\s+is\s+(up|down)", line.strip(), re.IGNORECASE)
                if not m:
                    continue
                ifname = m.group(1)
                status = m.group(2).lower()
                iface_id = f"IF-NXOS-{hostname}-{ifname}"
                try:
                    await neo4j_client.merge_node("Interface", iface_id, {
                        "id": iface_id, "name": ifname, "status": status,
                        "display_name": display_name.interface(ifname, device_dn),
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_INTERFACE", "Interface", iface_id)
                    result.record_success("interfaces")
                except Exception as e:
                    result.record_failure("interfaces", str(e))
        except Exception as e:
            result.record_failure("interfaces", str(e))

        # VLANs
        try:
            vlan_out = await asyncio.to_thread(self._run_ssh, "show vlan")
            for line in vlan_out.splitlines():
                m = re.match(r"^\s*(\d+)\s+(\S+)", line.strip())
                if not m:
                    continue
                vid = m.group(1)
                vlan_id = f"VLAN-{vid}"
                try:
                    await neo4j_client.merge_node("VLAN", vlan_id, {
                        "id": vlan_id, "vlan_id": int(vid),
                        "display_name": display_name.vlan(vid),
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HOSTS", "VLAN", vlan_id)
                    result.record_success("vlans")
                except Exception as e:
                    result.record_failure("vlans", str(e))
        except Exception as e:
            result.record_failure("vlans", str(e))

        # BGP peers
        try:
            bgp_out = await asyncio.to_thread(self._run_ssh, "show bgp summary")
            asn = ""
            for line in bgp_out.splitlines():
                am = re.search(r"local AS number\s+(\d+)", line, re.IGNORECASE)
                if am:
                    asn = am.group(1)
                bm = re.match(r"^(\d+\.\d+\.\d+\.\d+)\s+", line.strip())
                if bm and asn:
                    neighbor = _safe_id(bm.group(1))
                    bgp_id = f"BGP-{asn}-{neighbor}"
                    try:
                        await neo4j_client.merge_node("BGPPeer", bgp_id, {
                            "id": bgp_id, "asn": asn, "neighbor": bm.group(1),
                            "display_name": f"BGP Peer {bm.group(1)} (AS {asn})",
                        })
                        await neo4j_client.create_relationship("Device", device_id, "HAS_BGP_PEER", "BGPPeer", bgp_id)
                        result.record_success("bgp_peers")
                    except Exception as e:
                        result.record_failure("bgp_peers", str(e))
        except Exception as e:
            result.record_failure("bgp_peers", str(e))

        # VRFs
        try:
            vrf_out = await asyncio.to_thread(self._run_ssh, "show vrf")
            for line in vrf_out.splitlines():
                vm = re.match(r"^(\S+)\s+", line.strip())
                if not vm or vm.group(1).lower() in {"vrf-name", "---"}:
                    continue
                vrf_name = vm.group(1)
                vrf_id = f"VRF-{hostname}-{_safe_id(vrf_name)}"
                try:
                    await neo4j_client.merge_node("VRF", vrf_id, {
                        "id": vrf_id, "name": vrf_name,
                        "display_name": f"VRF {vrf_name}  (Cisco NX-OS \u2014 {hostname})",
                    })
                    await neo4j_client.create_relationship("Device", device_id, "HAS_VRF", "VRF", vrf_id)
                    result.record_success("vrfs")
                except Exception as e:
                    result.record_failure("vrfs", str(e))
        except Exception as e:
            result.record_failure("vrfs", str(e))

        result.finalise()
        return {"vendor": "cisco-nxos", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-nxos", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-nxos", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-nxos", "applied": False, "error": "not implemented"}
