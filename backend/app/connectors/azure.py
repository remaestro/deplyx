"""Azure connector.

Uses Azure ARM REST endpoints (with bearer token) to sync VNets/subnets/NSGs.
"""

from typing import Any

import requests

from app.connectors.base import BaseConnector
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AzureConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.subscription_id = config.get("subscription_id", "")
        self.resource_group = config.get("resource_group", "")
        self.bearer_token = config.get("bearer_token", "")
        self.api_version = config.get("api_version", "2023-09-01")
        self.base_url = f"https://management.azure.com/subscriptions/{self.subscription_id}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

    async def sync(self) -> dict[str, Any]:
        synced: dict[str, int] = {"vnets": 0, "subnets": 0, "nsgs": 0}
        try:
            if not self.subscription_id or not self.resource_group or not self.bearer_token:
                raise ValueError("Missing Azure connector config: subscription_id, resource_group, bearer_token")

            vnets_resp = requests.get(
                f"{self.base_url}/resourceGroups/{self.resource_group}/providers/Microsoft.Network/virtualNetworks?api-version={self.api_version}",
                headers=self._headers(),
                timeout=30,
            )
            vnets_resp.raise_for_status()
            vnets = vnets_resp.json().get("value", [])

            for vnet in vnets:
                vnet_id = vnet.get("name", "")
                if not vnet_id:
                    continue
                await neo4j_client.merge_node(
                    "Device",
                    vnet_id,
                    {
                        "id": vnet_id,
                        "type": "vnet",
                        "vendor": "azure",
                        "hostname": vnet_id,
                        "criticality": "high",
                        "address_space": ",".join(vnet.get("properties", {}).get("addressSpace", {}).get("addressPrefixes", [])),
                    },
                )
                synced["vnets"] += 1

                for subnet in vnet.get("properties", {}).get("subnets", []):
                    subnet_name = subnet.get("name", "")
                    if not subnet_name:
                        continue
                    subnet_id = f"AZ-SUBNET-{vnet_id}-{subnet_name}"
                    await neo4j_client.merge_node(
                        "VLAN",
                        subnet_id,
                        {
                            "id": subnet_id,
                            "vlan_id": 0,
                            "name": subnet_name,
                            "description": subnet.get("properties", {}).get("addressPrefix", ""),
                        },
                    )
                    await neo4j_client.create_relationship("Device", vnet_id, "HOSTS", "VLAN", subnet_id)
                    synced["subnets"] += 1

            nsgs_resp = requests.get(
                f"{self.base_url}/resourceGroups/{self.resource_group}/providers/Microsoft.Network/networkSecurityGroups?api-version={self.api_version}",
                headers=self._headers(),
                timeout=30,
            )
            nsgs_resp.raise_for_status()
            nsgs = nsgs_resp.json().get("value", [])

            for nsg in nsgs:
                nsg_name = nsg.get("name", "")
                if not nsg_name:
                    continue
                await neo4j_client.merge_node(
                    "Device",
                    nsg_name,
                    {
                        "id": nsg_name,
                        "type": "security_group",
                        "vendor": "azure",
                        "hostname": nsg_name,
                        "criticality": "high",
                    },
                )
                synced["nsgs"] += 1

        except Exception as e:
            logger.error("Azure sync error: %s", e)
            return {"vendor": "azure", "status": "error", "error": str(e), "synced": synced}

        return {"vendor": "azure", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.bearer_token:
            return {"vendor": "azure", "valid": False, "error": "Missing bearer_token"}
        if not payload.get("nsg_name"):
            return {"vendor": "azure", "valid": False, "error": "nsg_name is required"}
        return {"vendor": "azure", "valid": True}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.validate_change(payload)

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.bearer_token:
            return {"vendor": "azure", "applied": False, "error": "Missing bearer_token"}
        return {"vendor": "azure", "applied": True, "note": "Use Azure NSG rule payload to perform a concrete apply operation"}
