from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.rbac import Role, require_role
from app.core.security import get_current_user
from app.graph.seed import seed_graph
from app.schemas.graph import (
    ApplicationCreate,
    ApplicationRead,
    CableCreate,
    CableRead,
    DatacenterCreate,
    DatacenterRead,
    DeviceCreate,
    DeviceRead,
    GraphNode,
    IPCreate,
    IPRead,
    InterfaceCreate,
    InterfaceRead,
    PortCreate,
    PortRead,
    RelationshipCreate,
    RelationshipRead,
    RuleCreate,
    RuleRead,
    ServiceCreate,
    ServiceRead,
    TopologyResponse,
    VLANCreate,
    VLANRead,
)
from app.services import graph_service

router = APIRouter(prefix="/graph", tags=["graph"])

# ── Devices ────────────────────────────────────────────────────────────


@router.get("/devices", response_model=list[dict])
async def list_devices(_=Depends(get_current_user)):
    return await graph_service.list_devices()


@router.post("/devices", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_device(body: DeviceCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_device(body.model_dump())


@router.get("/devices/{device_id}", response_model=dict)
async def get_device(device_id: str, _=Depends(get_current_user)):
    device = await graph_service.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.put("/devices/{device_id}", response_model=dict)
async def update_device(device_id: str, body: DeviceCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    result = await graph_service.update_device(device_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return result


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_device(device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")


# ── Interfaces ─────────────────────────────────────────────────────────


@router.get("/interfaces", response_model=list[dict])
async def list_interfaces(_=Depends(get_current_user)):
    return await graph_service.list_interfaces()


@router.post("/interfaces", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_interface(body: InterfaceCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_interface(body.model_dump())


@router.get("/interfaces/{interface_id}", response_model=dict)
async def get_interface(interface_id: str, _=Depends(get_current_user)):
    interface = await graph_service.get_interface(interface_id)
    if interface is None:
        raise HTTPException(status_code=404, detail="Interface not found")
    return interface


@router.put("/interfaces/{interface_id}", response_model=dict)
async def update_interface(interface_id: str, body: InterfaceCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    result = await graph_service.update_interface(interface_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="Interface not found")
    return result


@router.delete("/interfaces/{interface_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interface(interface_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_interface(interface_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Interface not found")


# ── VLANs ──────────────────────────────────────────────────────────────


@router.get("/vlans", response_model=list[dict])
async def list_vlans(_=Depends(get_current_user)):
    return await graph_service.list_vlans()


@router.post("/vlans", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_vlan(body: VLANCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_vlan(body.model_dump())


@router.get("/vlans/{vlan_id}", response_model=dict)
async def get_vlan(vlan_id: str, _=Depends(get_current_user)):
    vlan = await graph_service.get_vlan(vlan_id)
    if vlan is None:
        raise HTTPException(status_code=404, detail="VLAN not found")
    return vlan


@router.put("/vlans/{vlan_id}", response_model=dict)
async def update_vlan(vlan_id: str, body: VLANCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    result = await graph_service.update_vlan(vlan_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="VLAN not found")
    return result


@router.delete("/vlans/{vlan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vlan(vlan_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_vlan(vlan_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="VLAN not found")


# ── IPs ───────────────────────────────────────────────────────────────


@router.get("/ips", response_model=list[dict])
async def list_ips(_=Depends(get_current_user)):
    return await graph_service.list_ips()


@router.post("/ips", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_ip(body: IPCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_ip(body.model_dump())


@router.get("/ips/{ip_id}", response_model=dict)
async def get_ip(ip_id: str, _=Depends(get_current_user)):
    ip = await graph_service.get_ip(ip_id)
    if ip is None:
        raise HTTPException(status_code=404, detail="IP not found")
    return ip


@router.put("/ips/{ip_id}", response_model=dict)
async def update_ip(ip_id: str, body: IPCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    result = await graph_service.update_ip(ip_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="IP not found")
    return result


@router.delete("/ips/{ip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ip(ip_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_ip(ip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="IP not found")


# ── Rules ──────────────────────────────────────────────────────────────


@router.get("/rules", response_model=list[dict])
async def list_rules(_=Depends(get_current_user)):
    return await graph_service.list_rules()


@router.post("/rules", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_rule(body: RuleCreate, _=Depends(require_role(Role.ADMIN, Role.SECURITY))):
    return await graph_service.create_rule(body.model_dump())


@router.get("/rules/{rule_id}", response_model=dict)
async def get_rule(rule_id: str, _=Depends(get_current_user)):
    rule = await graph_service.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.put("/rules/{rule_id}", response_model=dict)
async def update_rule(rule_id: str, body: RuleCreate, _=Depends(require_role(Role.ADMIN, Role.SECURITY))):
    result = await graph_service.update_rule(rule_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return result


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")


# ── Applications ───────────────────────────────────────────────────────


@router.get("/applications", response_model=list[dict])
async def list_applications(_=Depends(get_current_user)):
    return await graph_service.list_applications()


@router.post("/applications", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_application(body: ApplicationCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_application(body.model_dump())


@router.get("/applications/{app_id}", response_model=dict)
async def get_application(app_id: str, _=Depends(get_current_user)):
    app = await graph_service.get_application(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.put("/applications/{app_id}", response_model=dict)
async def update_application(app_id: str, body: ApplicationCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    result = await graph_service.update_application(app_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.delete("/applications/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(app_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_application(app_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")


# ── Services ───────────────────────────────────────────────────────────


@router.get("/services", response_model=list[dict])
async def list_services(_=Depends(get_current_user)):
    return await graph_service.list_services()


@router.post("/services", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_service(body: ServiceCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_service(body.model_dump())


@router.get("/services/{service_id}", response_model=dict)
async def get_service(service_id: str, _=Depends(get_current_user)):
    service = await graph_service.get_service(service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.put("/services/{service_id}", response_model=dict)
async def update_service(service_id: str, body: ServiceCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    result = await graph_service.update_service(service_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return result


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_service(service_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Service not found")


# ── Datacenters ───────────────────────────────────────────────────────


@router.get("/datacenters", response_model=list[dict])
async def list_datacenters(_=Depends(get_current_user)):
    return await graph_service.list_datacenters()


@router.post("/datacenters", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_datacenter(body: DatacenterCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_datacenter(body.model_dump())


@router.get("/datacenters/{datacenter_id}", response_model=dict)
async def get_datacenter(datacenter_id: str, _=Depends(get_current_user)):
    datacenter = await graph_service.get_datacenter(datacenter_id)
    if datacenter is None:
        raise HTTPException(status_code=404, detail="Datacenter not found")
    return datacenter


@router.put("/datacenters/{datacenter_id}", response_model=dict)
async def update_datacenter(datacenter_id: str, body: DatacenterCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    result = await graph_service.update_datacenter(datacenter_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="Datacenter not found")
    return result


@router.delete("/datacenters/{datacenter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_datacenter(datacenter_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_datacenter(datacenter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Datacenter not found")


# ── Ports ─────────────────────────────────────────────────────────────


@router.get("/ports", response_model=list[dict])
async def list_ports(_=Depends(get_current_user)):
    return await graph_service.list_ports()


@router.post("/ports", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_port(body: PortCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_port(body.model_dump())


@router.get("/ports/{port_id}", response_model=dict)
async def get_port(port_id: str, _=Depends(get_current_user)):
    port = await graph_service.get_port(port_id)
    if port is None:
        raise HTTPException(status_code=404, detail="Port not found")
    return port


@router.put("/ports/{port_id}", response_model=dict)
async def update_port(port_id: str, body: PortCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    result = await graph_service.update_port(port_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="Port not found")
    return result


@router.delete("/ports/{port_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_port(port_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_port(port_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Port not found")


# ── Cables ────────────────────────────────────────────────────────────


@router.get("/cables", response_model=list[dict])
async def list_cables(_=Depends(get_current_user)):
    return await graph_service.list_cables()


@router.post("/cables", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_cable(body: CableCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_cable(body.model_dump())


@router.get("/cables/{cable_id}", response_model=dict)
async def get_cable(cable_id: str, _=Depends(get_current_user)):
    cable = await graph_service.get_cable(cable_id)
    if cable is None:
        raise HTTPException(status_code=404, detail="Cable not found")
    return cable


@router.put("/cables/{cable_id}", response_model=dict)
async def update_cable(cable_id: str, body: CableCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    result = await graph_service.update_cable(cable_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="Cable not found")
    return result


@router.delete("/cables/{cable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cable(cable_id: str, _=Depends(require_role(Role.ADMIN))):
    deleted = await graph_service.delete_cable(cable_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cable not found")


# ── Relationships ──────────────────────────────────────────────────────


@router.post("/relationships", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_relationship(body: RelationshipCreate, _=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    return await graph_service.create_relationship(
        body.from_label, body.from_id, body.rel_type, body.to_label, body.to_id, body.properties
    )


# ── Topology ───────────────────────────────────────────────────────────


@router.get("/topology", response_model=TopologyResponse)
async def get_topology(
    center: str | None = Query(None, description="Center node ID for subgraph"),
    depth: int = Query(3, ge=1, le=10, description="Traversal depth"),
    _=Depends(get_current_user),
):
    return await graph_service.get_topology(center_id=center, depth=depth)


# ── Seed (admin only) ─────────────────────────────────────────────────


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed(_=Depends(require_role(Role.ADMIN))):
    counts = await seed_graph()
    return {"status": "seeded", "counts": counts}


# ── Search (for node picker) ──────────────────────────────────────────


@router.get("/search")
async def search_nodes(
    q: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(20, ge=1, le=100),
    _=Depends(get_current_user),
):
    results = await graph_service.search_nodes(q, limit)
    return results
