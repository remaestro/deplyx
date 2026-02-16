from typing import Any

from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ── Device CRUD ────────────────────────────────────────────────────────


async def create_device(props: dict[str, Any]) -> dict[str, Any]:
    return await neo4j_client.merge_node("Device", props["id"], props)


async def get_device(device_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("Device", device_id)


async def list_devices() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("Device")


async def update_device(device_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("Device", device_id, props)


async def delete_device(device_id: str) -> bool:
    return await neo4j_client.delete_node("Device", device_id)


# ── Interface CRUD ─────────────────────────────────────────────────────


async def create_interface(props: dict[str, Any]) -> dict[str, Any]:
    node = await neo4j_client.merge_node("Interface", props["id"], props)
    if props.get("device_id"):
        await neo4j_client.create_relationship("Device", props["device_id"], "HAS_INTERFACE", "Interface", props["id"])
        await neo4j_client.create_relationship("Interface", props["id"], "PART_OF", "Device", props["device_id"])
    return node


async def list_interfaces() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("Interface")


async def get_interface(interface_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("Interface", interface_id)


async def update_interface(interface_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("Interface", interface_id, props)


async def delete_interface(interface_id: str) -> bool:
    return await neo4j_client.delete_node("Interface", interface_id)


# ── VLAN CRUD ──────────────────────────────────────────────────────────


async def create_vlan(props: dict[str, Any]) -> dict[str, Any]:
    return await neo4j_client.merge_node("VLAN", props["id"], props)


async def list_vlans() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("VLAN")


async def get_vlan(vlan_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("VLAN", vlan_id)


async def update_vlan(vlan_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("VLAN", vlan_id, props)


async def delete_vlan(vlan_id: str) -> bool:
    return await neo4j_client.delete_node("VLAN", vlan_id)


# ── IP CRUD ────────────────────────────────────────────────────────────


async def create_ip(props: dict[str, Any]) -> dict[str, Any]:
    return await neo4j_client.merge_node("IP", props["id"], props)


async def list_ips() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("IP")


async def get_ip(ip_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("IP", ip_id)


async def update_ip(ip_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("IP", ip_id, props)


async def delete_ip(ip_id: str) -> bool:
    return await neo4j_client.delete_node("IP", ip_id)


# ── Rule CRUD ──────────────────────────────────────────────────────────


async def create_rule(props: dict[str, Any]) -> dict[str, Any]:
    device_id = props.get("device_id", "")
    node = await neo4j_client.merge_node("Rule", props["id"], props)
    if device_id:
        await neo4j_client.create_relationship("Device", device_id, "HAS_RULE", "Rule", props["id"])
    return node


async def get_rule(rule_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("Rule", rule_id)


async def list_rules() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("Rule")


async def update_rule(rule_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("Rule", rule_id, props)


async def delete_rule(rule_id: str) -> bool:
    return await neo4j_client.delete_node("Rule", rule_id)


# ── Application CRUD ──────────────────────────────────────────────────


async def create_application(props: dict[str, Any]) -> dict[str, Any]:
    return await neo4j_client.merge_node("Application", props["id"], props)


async def get_application(app_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("Application", app_id)


async def list_applications() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("Application")


async def update_application(app_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("Application", app_id, props)


async def delete_application(app_id: str) -> bool:
    return await neo4j_client.delete_node("Application", app_id)


# ── Service CRUD ───────────────────────────────────────────────────────


async def create_service(props: dict[str, Any]) -> dict[str, Any]:
    return await neo4j_client.merge_node("Service", props["id"], props)


async def list_services() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("Service")


async def get_service(service_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("Service", service_id)


async def update_service(service_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("Service", service_id, props)


async def delete_service(service_id: str) -> bool:
    return await neo4j_client.delete_node("Service", service_id)


# ── Datacenter CRUD ───────────────────────────────────────────────────


async def create_datacenter(props: dict[str, Any]) -> dict[str, Any]:
    return await neo4j_client.merge_node("Datacenter", props["id"], props)


async def list_datacenters() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("Datacenter")


async def get_datacenter(datacenter_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("Datacenter", datacenter_id)


async def update_datacenter(datacenter_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("Datacenter", datacenter_id, props)


async def delete_datacenter(datacenter_id: str) -> bool:
    return await neo4j_client.delete_node("Datacenter", datacenter_id)


# ── Port CRUD ─────────────────────────────────────────────────────────


async def create_port(props: dict[str, Any]) -> dict[str, Any]:
    node = await neo4j_client.merge_node("Port", props["id"], props)
    if props.get("device_id"):
        await neo4j_client.create_relationship("Port", props["id"], "PART_OF", "Device", props["device_id"])
    return node


async def get_port(port_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("Port", port_id)


async def list_ports() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("Port")


async def update_port(port_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("Port", port_id, props)


async def delete_port(port_id: str) -> bool:
    return await neo4j_client.delete_node("Port", port_id)


# ── Cable CRUD ────────────────────────────────────────────────────────


async def create_cable(props: dict[str, Any]) -> dict[str, Any]:
    node = await neo4j_client.merge_node("Cable", props["id"], props)
    from_device_id = props.get("from_device_id")
    to_device_id = props.get("to_device_id")
    if from_device_id:
        await neo4j_client.create_relationship("Cable", props["id"], "CONNECTED_TO", "Device", from_device_id)
    if to_device_id:
        await neo4j_client.create_relationship("Cable", props["id"], "CONNECTED_TO", "Device", to_device_id)
    return node


async def get_cable(cable_id: str) -> dict[str, Any] | None:
    return await neo4j_client.get_node("Cable", cable_id)


async def list_cables() -> list[dict[str, Any]]:
    return await neo4j_client.get_all_nodes("Cable")


async def update_cable(cable_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
    return await neo4j_client.update_node("Cable", cable_id, props)


async def delete_cable(cable_id: str) -> bool:
    return await neo4j_client.delete_node("Cable", cable_id)


# ── Relationship ──────────────────────────────────────────────────────


async def create_relationship(
    from_label: str, from_id: str, rel_type: str, to_label: str, to_id: str, props: dict[str, Any] | None = None
) -> dict[str, Any]:
    return await neo4j_client.create_relationship(from_label, from_id, rel_type, to_label, to_id, props)


# ── Topology ──────────────────────────────────────────────────────────


async def get_topology(center_id: str | None = None, depth: int = 3) -> dict[str, Any]:
    if center_id:
        return await neo4j_client.get_impact_subgraph(center_id, depth)
    return await neo4j_client.get_full_topology()


# ── Search ────────────────────────────────────────────────────────────


async def search_nodes(query: str, limit: int = 20) -> list[dict[str, Any]]:
    return await neo4j_client.search_nodes(query, limit)
