from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────


class DeviceType(StrEnum):
    FIREWALL = "firewall"
    SWITCH = "switch"
    ROUTER = "router"
    RACK = "rack"
    PATCH_PANEL = "patch_panel"
    LOAD_BALANCER = "load_balancer"
    SERVER = "server"
    CLOUD_GATEWAY = "cloud_gateway"
    WIRELESS_AP = "wireless_ap"
    WIRELESS_CONTROLLER = "wireless_controller"


class RuleAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class Criticality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Node schemas ───────────────────────────────────────────────────────


class DeviceCreate(BaseModel):
    id: str = Field(..., description="Unique device identifier, e.g. FW-DC1-01")
    type: DeviceType
    vendor: str = ""
    hostname: str = ""
    location: str = ""
    criticality: Criticality = Criticality.MEDIUM
    metadata: dict[str, Any] = {}


class DeviceRead(DeviceCreate):
    pass


class InterfaceCreate(BaseModel):
    id: str
    name: str = ""
    speed: str = ""
    status: str = "up"
    device_id: str = Field(..., description="Parent device id")


class InterfaceRead(InterfaceCreate):
    pass


class VLANCreate(BaseModel):
    id: str
    vlan_id: int
    name: str = ""
    description: str = ""


class VLANRead(VLANCreate):
    pass


class IPCreate(BaseModel):
    id: str
    address: str
    subnet: str = ""
    version: int = 4


class IPRead(IPCreate):
    pass


class RuleCreate(BaseModel):
    id: str
    name: str = ""
    source: str = ""
    destination: str = ""
    port: str = ""
    protocol: str = "tcp"
    action: RuleAction = RuleAction.ALLOW
    device_id: str = Field(..., description="Firewall device that owns this rule")


class RuleRead(RuleCreate):
    pass


class ApplicationCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    criticality: Criticality = Criticality.MEDIUM
    owner: str = ""


class ApplicationRead(ApplicationCreate):
    pass


class ServiceCreate(BaseModel):
    id: str
    name: str
    port: int
    protocol: str = "tcp"


class ServiceRead(ServiceCreate):
    pass


class DatacenterCreate(BaseModel):
    id: str
    name: str
    location: str = ""


class DatacenterRead(DatacenterCreate):
    pass


class CableCreate(BaseModel):
    id: str
    cable_type: str = "fiber"
    from_device_id: str = ""
    to_device_id: str = ""


class CableRead(CableCreate):
    pass


class PortCreate(BaseModel):
    id: str
    number: int
    port_type: str = "ethernet"
    status: str = "up"
    device_id: str = ""


class PortRead(PortCreate):
    pass


# ── Relationship ───────────────────────────────────────────────────────


class RelationshipCreate(BaseModel):
    from_label: str
    from_id: str
    rel_type: str = Field(..., description="e.g. CONNECTED_TO, HOSTS, ROUTES_TO, PROTECTS, DEPENDS_ON, LOCATED_IN, PART_OF")
    to_label: str
    to_id: str
    properties: dict[str, Any] = {}


class RelationshipRead(RelationshipCreate):
    pass


# ── Topology response (for frontend graph view) ───────────────────────


class GraphNode(BaseModel):
    id: str
    label: str  # Neo4j label: Device, Application, etc.
    properties: dict[str, Any] = {}


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    rel_type: str
    properties: dict[str, Any] = {}


class TopologyResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
