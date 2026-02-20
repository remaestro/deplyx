"""Lab emulation API.

Manages virtual network lab containers via the Docker SDK.
Each container represents a mock device (firewall, switch, router, app…)
running on the isolated `lab-net` Docker network.

Routes:
  GET    /lab/catalog                          → full component catalogue
  GET    /lab/containers                       → list active lab containers + status
  POST   /lab/containers                       → spawn a new container
  DELETE /lab/containers/{id}                  → remove container
  POST   /lab/containers/{id}/start            → start stopped container
  POST   /lab/containers/{id}/stop             → stop running container
  POST   /lab/containers/{id}/restart          → restart container
  GET    /lab/containers/{id}/logs             → last 150 lines of logs

"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.rbac import Role, require_role
from fastapi import Depends

router = APIRouter(prefix="/lab", tags=["lab"])

# ---------------------------------------------------------------------------
# Docker client (lazy) — won't fail at import time if Docker isn't available
# ---------------------------------------------------------------------------

def _get_docker():
    try:
        import docker  # type: ignore
        return docker.from_env()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {exc}")


# ---------------------------------------------------------------------------
# Component catalogue
# ---------------------------------------------------------------------------

CATALOG: list[dict[str, Any]] = [
    # ── Firewalls ──────────────────────────────────────────────────────────
    {
        "type_id": "fortinet",
        "label": "FortiGate Firewall",
        "category": "Firewall",
        "vendor": "Fortinet",
        "model": "FortiGate 60F",
        "description": "FortiOS REST API (system status, interfaces, firewall policies)",
        "icon_type": "firewall",
        "image": "deplyx-lab-mock-fortinet",
        "build_context": "mock-fortinet",
        "protocol": "HTTPS API",
        "default_port": 443,
        "default_env": {
            "FORTINET_API_TOKEN": "fg-lab-token-001",
            "FORTINET_HOSTNAME": "FG-LAB-{name}",
            "FORTINET_SERIAL": "FGT60F0000000001",
        },
        "color": "#ef4444",
    },
    {
        "type_id": "paloalto",
        "label": "PAN-OS Firewall",
        "category": "Firewall",
        "vendor": "Palo Alto Networks",
        "model": "PA-850",
        "description": "PAN-OS XML + REST API (system info, interfaces, security rules)",
        "icon_type": "firewall",
        "image": "deplyx-lab-mock-paloalto",
        "build_context": "mock-paloalto",
        "protocol": "HTTPS API",
        "default_port": 443,
        "default_env": {
            "PALOALTO_API_KEY": "pa-lab-apikey-001",
            "PALOALTO_HOSTNAME": "PA-LAB-{name}",
            "PALOALTO_SERIAL": "007200001234",
        },
        "color": "#ef4444",
    },
    {
        "type_id": "checkpoint",
        "label": "Check Point Gateway",
        "category": "Firewall",
        "vendor": "Check Point",
        "model": "R81.20",
        "description": "Check Point Web API (login/session, gateways, access rulebase)",
        "icon_type": "firewall",
        "image": "deplyx-lab-mock-checkpoint",
        "build_context": "mock-checkpoint",
        "protocol": "HTTPS API",
        "default_port": 443,
        "default_env": {
            "CHECKPOINT_USER": "admin",
            "CHECKPOINT_PASS": "Cp@ssw0rd!",
            "CHECKPOINT_HOSTNAME": "CP-LAB-{name}",
        },
        "color": "#ef4444",
    },
    # ── Switches ───────────────────────────────────────────────────────────
    {
        "type_id": "cisco-ios",
        "label": "Cisco IOS Switch",
        "category": "Switch",
        "vendor": "Cisco",
        "model": "Catalyst 9300",
        "description": "IOS SSH + NAPALM (show version, interfaces, VLANs, running-config, ARP)",
        "icon_type": "switch",
        "image": "deplyx-lab-mock-cisco",
        "build_context": "mock-cisco",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "CISCO_HOSTNAME": "SW-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "Cisco123!",
            "SSH_PORT": "22",
        },
        "color": "#1d4ed8",
    },
    {
        "type_id": "cisco-nxos",
        "label": "Cisco NX-OS Switch",
        "category": "Switch",
        "vendor": "Cisco",
        "model": "Nexus 9000",
        "description": "NX-OS SSH + NAPALM (show version, interfaces, VLANs, VRF, BGP)",
        "icon_type": "switch",
        "image": "deplyx-lab-mock-cisco-nxos",
        "build_context": "mock-cisco-nxos",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "NXOS_HOSTNAME": "NXOS-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "Cisco123!",
            "SSH_PORT": "22",
        },
        "color": "#1d4ed8",
    },
    {
        "type_id": "juniper",
        "label": "Juniper EX Switch",
        "category": "Switch",
        "vendor": "Juniper",
        "model": "EX4300",
        "description": "JunOS SSH + NAPALM (show version, interfaces, VLANs, route, ARP, LLDP)",
        "icon_type": "switch",
        "image": "deplyx-lab-mock-juniper",
        "build_context": "mock-juniper",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "JUNIPER_HOSTNAME": "SW-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "Juniper123!",
            "SSH_PORT": "22",
        },
        "color": "#16a34a",
    },
    {
        "type_id": "aruba-switch",
        "label": "Aruba Switch",
        "category": "Switch",
        "vendor": "Aruba / HP",
        "model": "CX 6300",
        "description": "ArubaOS SSH (show version, interfaces, VLANs, spanning-tree, LLDP)",
        "icon_type": "switch",
        "image": "deplyx-lab-mock-aruba-switch",
        "build_context": "mock-aruba-switch",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "ARUBA_HOSTNAME": "SW-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "Aruba123!",
            "SSH_PORT": "22",
        },
        "color": "#0891b2",
    },
    # ── Routers ────────────────────────────────────────────────────────────
    {
        "type_id": "cisco-router",
        "label": "Cisco IOS Router",
        "category": "Router",
        "vendor": "Cisco",
        "model": "ISR 4451",
        "description": "IOS SSH (show ip route, BGP, OSPF, interfaces, NAT, ACLs)",
        "icon_type": "router",
        "image": "deplyx-lab-mock-router",
        "build_context": "mock-router",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "ROUTER_HOSTNAME": "RT-LAB-{name}",
            "ROUTER_VENDOR": "cisco",
            "SSH_USER": "admin",
            "SSH_PASS": "Cisco123!",
            "SSH_PORT": "22",
        },
        "color": "#7c3aed",
    },
    {
        "type_id": "vyos",
        "label": "VyOS Router",
        "category": "Router",
        "vendor": "VyOS",
        "model": "VyOS 1.4",
        "description": "VyOS SSH (show interfaces, routing, bgp, firewall, nat, vpn)",
        "icon_type": "router",
        "image": "deplyx-lab-mock-vyos",
        "build_context": "mock-vyos",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "VYOS_HOSTNAME": "RT-LAB-{name}",
            "SSH_USER": "vyos",
            "SSH_PASS": "VyOS123!",
            "SSH_PORT": "22",
        },
        "color": "#7c3aed",
    },
    # ── Wireless ───────────────────────────────────────────────────────────
    {
        "type_id": "cisco-wlc",
        "label": "Cisco Wireless Controller",
        "category": "Wireless",
        "vendor": "Cisco",
        "model": "WLC 9800",
        "description": "WLC SSH (show wlan summary, AP associations, client count, SSID config)",
        "icon_type": "wireless_controller",
        "image": "deplyx-lab-mock-wlc",
        "build_context": "mock-wlc",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "WLC_HOSTNAME": "WLC-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "Wireless123!",
            "SSH_PORT": "22",
        },
        "color": "#d97706",
    },
    {
        "type_id": "aruba-ap",
        "label": "Aruba Access Point",
        "category": "Wireless",
        "vendor": "Aruba",
        "model": "AP-515",
        "description": "Aruba AP SSH (show ap bss-table, show ap radio-summary, SSID clients)",
        "icon_type": "wireless_ap",
        "image": "deplyx-lab-mock-aruba-ap",
        "build_context": "mock-aruba-ap",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "AP_HOSTNAME": "AP-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "Aruba123!",
            "SSH_PORT": "22",
        },
        "color": "#d97706",
    },
    # ── Security ───────────────────────────────────────────────────────────
    {
        "type_id": "strongswan-vpn",
        "label": "StrongSwan VPN",
        "category": "Security",
        "vendor": "StrongSwan",
        "model": "VPN Gateway",
        "description": "IPsec VPN SSH (ipsec status, activeConnections, tunnel stats)",
        "icon_type": "vpn",
        "image": "deplyx-lab-mock-vpn",
        "build_context": "mock-vpn",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "VPN_HOSTNAME": "VPN-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "VPN123!",
            "SSH_PORT": "22",
        },
        "color": "#dc2626",
    },
    {
        "type_id": "snort-ids",
        "label": "Snort IDS",
        "category": "Security",
        "vendor": "Snort / Cisco",
        "model": "Snort 3",
        "description": "IDS SSH (snort -s alerts, top signatures, blocked IPs, interface stats)",
        "icon_type": "ids",
        "image": "deplyx-lab-mock-snort",
        "build_context": "mock-snort",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "IDS_HOSTNAME": "IDS-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "Snort123!",
            "SSH_PORT": "22",
        },
        "color": "#dc2626",
    },
    {
        "type_id": "openldap",
        "label": "OpenLDAP / AD",
        "category": "Security",
        "vendor": "OpenLDAP",
        "model": "LDAP Directory",
        "description": "SSH (ldapsearch, slapd status, replica status, schema info)",
        "icon_type": "ldap",
        "image": "deplyx-lab-mock-ldap",
        "build_context": "mock-ldap",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "LDAP_HOSTNAME": "LDAP-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "LDAP123!",
            "SSH_PORT": "22",
        },
        "color": "#0284c7",
    },
    # ── Applications ───────────────────────────────────────────────────────
    {
        "type_id": "nginx",
        "label": "Nginx Web Server",
        "category": "Application",
        "vendor": "Nginx",
        "model": "nginx 1.25",
        "description": "Real nginx (serves HTTP on 80). SSH shows access_log, error_log, nginx -T config.",
        "icon_type": "webserver",
        "image": "deplyx-lab-mock-nginx",
        "build_context": "mock-nginx",
        "protocol": "SSH + HTTP",
        "default_port": 22,
        "default_env": {
            "APP_HOSTNAME": "WEB-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "App123!",
            "SSH_PORT": "22",
        },
        "color": "#059669",
    },
    {
        "type_id": "postgres",
        "label": "PostgreSQL Database",
        "category": "Application",
        "vendor": "PostgreSQL",
        "model": "PostgreSQL 16",
        "description": "SSH (psql show databases/tables, pg_stat_activity, replication status)",
        "icon_type": "database",
        "image": "deplyx-lab-mock-postgres",
        "build_context": "mock-postgres",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "APP_HOSTNAME": "DB-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "App123!",
            "SSH_PORT": "22",
        },
        "color": "#2563eb",
    },
    {
        "type_id": "redis",
        "label": "Redis Cache",
        "category": "Application",
        "vendor": "Redis",
        "model": "Redis 7",
        "description": "SSH (redis-cli INFO, CONFIG GET, keyspace stats, clients, memory)",
        "icon_type": "cache",
        "image": "deplyx-lab-mock-redis-node",
        "build_context": "mock-redis-node",
        "protocol": "SSH",
        "default_port": 22,
        "default_env": {
            "APP_HOSTNAME": "CACHE-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "App123!",
            "SSH_PORT": "22",
        },
        "color": "#dc2626",
    },
    {
        "type_id": "elasticsearch",
        "label": "Elasticsearch",
        "category": "Application",
        "vendor": "Elastic",
        "model": "Elasticsearch 8",
        "description": "SSH (curl /_cat/indices, /_cluster/health, /_nodes/stats)",
        "icon_type": "database",
        "image": "deplyx-lab-mock-elasticsearch",
        "build_context": "mock-elasticsearch",
        "protocol": "SSH + HTTP",
        "default_port": 22,
        "default_env": {
            "APP_HOSTNAME": "ES-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "App123!",
            "SSH_PORT": "22",
        },
        "color": "#f59e0b",
    },
    {
        "type_id": "grafana",
        "label": "Grafana Monitoring",
        "category": "Application",
        "vendor": "Grafana Labs",
        "model": "Grafana 10",
        "description": "SSH (grafana-cli info, datasources, dashboard count, alert status)",
        "icon_type": "monitoring",
        "image": "deplyx-lab-mock-grafana",
        "build_context": "mock-grafana",
        "protocol": "SSH + HTTP",
        "default_port": 22,
        "default_env": {
            "APP_HOSTNAME": "MON-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "App123!",
            "SSH_PORT": "22",
        },
        "color": "#f59e0b",
    },
    {
        "type_id": "prometheus",
        "label": "Prometheus",
        "category": "Application",
        "vendor": "CNCF",
        "model": "Prometheus 2",
        "description": "SSH (promtool check config, targets status, scrape intervals, alerts)",
        "icon_type": "monitoring",
        "image": "deplyx-lab-mock-prometheus",
        "build_context": "mock-prometheus",
        "protocol": "SSH + HTTP",
        "default_port": 22,
        "default_env": {
            "APP_HOSTNAME": "PROM-LAB-{name}",
            "SSH_USER": "admin",
            "SSH_PASS": "App123!",
            "SSH_PORT": "22",
        },
        "color": "#f97316",
    },
]

CATALOG_BY_ID = {c["type_id"]: c for c in CATALOG}

# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

LAB_LABEL = "deplyx.lab"
LAB_NETWORK = os.getenv("LAB_NETWORK_NAME", "deplyx-lab-net")
LAB_DIR = os.getenv("LAB_DIR", "/lab")


def _ensure_network(client) -> None:
    """Create the lab bridge network if it doesn't already exist."""
    try:
        client.networks.get(LAB_NETWORK)
    except Exception:
        try:
            client.networks.create(
                LAB_NETWORK,
                driver="bridge",
                labels={LAB_LABEL: "true"},
            )
        except Exception:
            pass  # may have been created concurrently


def _ensure_image(client, image_name: str, build_context: str) -> None:
    """Build the image locally from /lab/<build_context> if not already present."""
    try:
        client.images.get(image_name)
        return  # already exists locally
    except Exception:
        pass

    build_path = os.path.join(LAB_DIR, build_context)
    if not os.path.isdir(build_path):
        raise HTTPException(
            status_code=503,
            detail=(
                f"Image {image_name!r} not found locally and build context "
                f"{build_path!r} does not exist. "
                "Make sure the lab/ directory is mounted at /lab inside the backend container."
            ),
        )
    try:
        client.images.build(path=build_path, tag=image_name, rm=True, pull=False)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build image {image_name!r}: {exc}",
        )


def _container_info(c) -> dict[str, Any]:
    """Serialise a docker Container object to a plain dict."""
    labels = c.labels or {}
    ports = c.ports or {}

    # Flatten port bindings → list[str]
    port_list: list[str] = []
    for internal, bindings in ports.items():
        if bindings:
            for b in bindings:
                port_list.append(f"{b['HostPort']}→{internal}")
        else:
            port_list.append(internal)

    # IP on lab-net
    ip = ""
    try:
        nets = c.attrs.get("NetworkSettings", {}).get("Networks", {})
        for net_name, net_data in nets.items():
            if "lab" in net_name.lower():
                ip = net_data.get("IPAddress", "")
                break
        if not ip:
            # fallback: first network
            for net_data in nets.values():
                ip = net_data.get("IPAddress", "")
                if ip:
                    break
    except Exception:
        pass

    return {
        "id": c.id[:12],
        "full_id": c.id,
        "name": c.name,
        "status": c.status,           # running | stopped | exited | created …
        "type_id": labels.get("deplyx.type", ""),
        "category": labels.get("deplyx.category", ""),
        "image": c.image.tags[0] if c.image.tags else labels.get("deplyx.image", ""),
        "ip": ip,
        "ports": port_list,
        "created": c.attrs.get("Created", ""),
        "labels": {k: v for k, v in labels.items() if k.startswith("deplyx.")},
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/catalog")
async def get_catalog():
    """Return the full component catalogue grouped by category."""
    return CATALOG


@router.get("/containers")
async def list_containers(_=Depends(require_role(Role.ADMIN, Role.NETWORK))):
    """List all deplyx lab containers and their live Docker status."""
    client = _get_docker()
    containers = client.containers.list(
        all=True,
        filters={"label": f"{LAB_LABEL}=true"},
    )
    return [_container_info(c) for c in containers]


class SpawnRequest(BaseModel):
    type_id: str
    name: str
    custom_env: dict[str, str] = {}


@router.post("/containers", status_code=201)
async def spawn_container(
    body: SpawnRequest,
    _=Depends(require_role(Role.ADMIN)),
):
    """Spawn a new lab container from the catalogue."""
    spec = CATALOG_BY_ID.get(body.type_id)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"Unknown type_id: {body.type_id!r}")

    client = _get_docker()

    # Build env vars — substitute {name} placeholder
    env: dict[str, str] = {}
    for k, v in spec["default_env"].items():
        env[k] = str(v).replace("{name}", body.name.upper())
    env.update(body.custom_env)

    # Safe container name: lowercase, alphanumeric + hyphens
    safe_name = f"lab-{body.type_id}-{body.name}".lower().replace("_", "-").replace(" ", "-")
    # Trim to 63 chars (Docker limit)
    safe_name = safe_name[:63]

    labels = {
        LAB_LABEL: "true",
        "deplyx.type": body.type_id,
        "deplyx.category": spec["category"],
        "deplyx.image": spec["image"],
        "deplyx.user_name": body.name,
    }

    # Build image locally if not available, then ensure network exists
    _ensure_image(client, spec["image"], spec.get("build_context", ""))
    _ensure_network(client)

    try:
        container = client.containers.run(
            image=spec["image"],
            name=safe_name,
            detach=True,
            environment=env,
            labels=labels,
            network=LAB_NETWORK,
            restart_policy={"Name": "unless-stopped"},
        )
        return _container_info(container)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/containers/{container_id}", status_code=204)
async def remove_container(
    container_id: str,
    _=Depends(require_role(Role.ADMIN)),
):
    """Stop and remove a lab container."""
    client = _get_docker()
    try:
        c = client.containers.get(container_id)
        _assert_lab_container(c)
        c.remove(force=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/containers/{container_id}/start")
async def start_container(
    container_id: str,
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    client = _get_docker()
    c = _get_lab_container(client, container_id)
    try:
        c.start()
        c.reload()
        return _container_info(c)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/containers/{container_id}/stop")
async def stop_container(
    container_id: str,
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    client = _get_docker()
    c = _get_lab_container(client, container_id)
    try:
        c.stop(timeout=5)
        c.reload()
        return _container_info(c)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/containers/{container_id}/restart")
async def restart_container(
    container_id: str,
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    client = _get_docker()
    c = _get_lab_container(client, container_id)
    try:
        c.restart(timeout=5)
        c.reload()
        return _container_info(c)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/containers/{container_id}/logs")
async def container_logs(
    container_id: str,
    lines: int = 150,
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    client = _get_docker()
    c = _get_lab_container(client, container_id)
    try:
        raw = c.logs(tail=lines, timestamps=True)
        log_text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        return {"container_id": container_id, "lines": log_text.splitlines()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Safety helpers — only operate on containers with the lab label
# ---------------------------------------------------------------------------

def _get_lab_container(client, container_id: str):
    try:
        c = client.containers.get(container_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _assert_lab_container(c)
    return c


def _assert_lab_container(c) -> None:
    """Raise 403 if the container is not a deplyx lab container."""
    if (c.labels or {}).get(LAB_LABEL) != "true":
        raise HTTPException(
            status_code=403,
            detail="Container is not a deplyx lab container — refusing to operate on it.",
        )


# ---------------------------------------------------------------------------
# Interactive terminal — execute queries against lab devices
# ---------------------------------------------------------------------------

# Command registry per device type — maps friendly commands to actions
# For HTTPS-API devices (fortinet, paloalto, checkpoint) we translate
# human-readable commands into REST calls.
# For SSH devices (cisco*, juniper) we proxy directly over SSH.

API_DEVICE_TYPES = {"fortinet", "paloalto", "checkpoint"}
SSH_DEVICE_TYPES = {"cisco-ios", "cisco-nxos", "cisco-router", "juniper"}

FORTINET_COMMANDS: dict[str, dict[str, Any]] = {
    "show system status":    {"method": "GET", "path": "/api/v2/monitor/system/status"},
    "show interfaces":       {"method": "GET", "path": "/api/v2/cmdb/system/interface"},
    "show firewall policies":{"method": "GET", "path": "/api/v2/cmdb/firewall/policy"},
    "show firewall policy":  {"method": "GET", "path": "/api/v2/cmdb/firewall/policy"},
}

PALOALTO_COMMANDS: dict[str, dict[str, Any]] = {
    "show system info":      {"method": "XML", "cmd": "<show><system><info></info></system></show>"},
    "show interfaces":       {"method": "XML", "cmd": "<show><interface></interface></show>"},
    "show security rules":   {"method": "REST", "path": "/restapi/v10.1/Policies/SecurityRules"},
    "validate config":       {"method": "XML", "cmd": "<validate></validate>"},
}

CHECKPOINT_COMMANDS: dict[str, dict[str, Any]] = {
    "show gateways":         {"method": "POST", "path": "/web_api/show-simple-gateways", "body": {}},
    "show access rules":     {"method": "POST", "path": "/web_api/show-access-rulebase",
                              "body": {"name": "Network", "offset": 0, "limit": 50}},
}

COMMAND_REGISTRY: dict[str, dict[str, dict[str, Any]]] = {
    "fortinet": FORTINET_COMMANDS,
    "paloalto": PALOALTO_COMMANDS,
    "checkpoint": CHECKPOINT_COMMANDS,
}


def _get_container_meta(c) -> dict[str, Any]:
    """Extract device type, IP, env vars from a container."""
    labels = c.labels or {}
    type_id = labels.get("deplyx.type", "")

    # IP on lab-net
    ip = ""
    try:
        nets = c.attrs.get("NetworkSettings", {}).get("Networks", {})
        for net_name, net_data in nets.items():
            if "lab" in net_name.lower():
                ip = net_data.get("IPAddress", "")
                break
        if not ip:
            for net_data in nets.values():
                ip = net_data.get("IPAddress", "")
                if ip:
                    break
    except Exception:
        pass

    # Parse env vars from container inspect
    env_list = c.attrs.get("Config", {}).get("Env", [])
    env: dict[str, str] = {}
    for e in env_list:
        if "=" in e:
            k, v = e.split("=", 1)
            env[k] = v

    return {"type_id": type_id, "ip": ip, "env": env}


def _https_get(host: str, path: str, headers: dict[str, str]) -> dict[str, Any]:
    """Make an HTTPS GET to a lab device (skip SSL verify)."""
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        resp = requests.get(f"https://{host}{path}", headers=headers,
                            verify=False, timeout=15)
        try:
            return {"status": resp.status_code, "data": resp.json()}
        except Exception:
            return {"status": resp.status_code, "data": resp.text}
    except Exception as exc:
        return {"status": 0, "error": str(exc)}


def _https_post(host: str, path: str, headers: dict[str, str],
                body: dict[str, Any]) -> dict[str, Any]:
    """Make an HTTPS POST to a lab device."""
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        resp = requests.post(f"https://{host}{path}", headers=headers,
                             json=body, verify=False, timeout=15)
        try:
            return {"status": resp.status_code, "data": resp.json()}
        except Exception:
            return {"status": resp.status_code, "data": resp.text}
    except Exception as exc:
        return {"status": 0, "error": str(exc)}


def _exec_fortinet(ip: str, env: dict[str, str], command: str) -> dict[str, Any]:
    """Execute a Fortinet REST API query."""
    token = env.get("FORTINET_API_TOKEN", "fg-lab-token-001")
    headers = {"Authorization": f"Bearer {token}"}

    spec = FORTINET_COMMANDS.get(command)
    if spec:
        return _https_get(ip, spec["path"], headers)

    # Flexible: allow raw API path like "GET /api/v2/..."
    if command.startswith("GET /"):
        path = command[4:].strip()
        return _https_get(ip, path, headers)

    return {"error": f"Unknown command. Available: {', '.join(FORTINET_COMMANDS.keys())}"}


def _exec_paloalto(ip: str, env: dict[str, str], command: str) -> dict[str, Any]:
    """Execute a Palo Alto API query."""
    api_key = env.get("PALOALTO_API_KEY", "pa-lab-apikey-001")

    spec = PALOALTO_COMMANDS.get(command)
    if not spec:
        if command.startswith("GET /"):
            path = command[4:].strip()
            return _https_get(ip, path, {"X-PAN-KEY": api_key})
        return {"error": f"Unknown command. Available: {', '.join(PALOALTO_COMMANDS.keys())}"}

    if spec["method"] == "XML":
        cmd_xml = quote(spec["cmd"])
        url = f"/api/?type=op&cmd={cmd_xml}&key={api_key}"
        result = _https_get(ip, url, {})
        # Parse XML response into a more readable dict
        if isinstance(result.get("data"), str):
            try:
                root = ET.fromstring(result["data"])
                result["data"] = _xml_to_dict(root)
            except Exception:
                pass
        return result
    elif spec["method"] == "REST":
        return _https_get(ip, spec["path"], {"X-PAN-KEY": api_key})

    return result


def _exec_checkpoint(ip: str, env: dict[str, str], command: str) -> dict[str, Any]:
    """Execute a Check Point API query (with auto-login/logout)."""
    user = env.get("CHECKPOINT_USER", "admin")
    password = env.get("CHECKPOINT_PASS", "Cp@ssw0rd!")

    spec = CHECKPOINT_COMMANDS.get(command)
    if not spec:
        return {"error": f"Unknown command. Available: {', '.join(CHECKPOINT_COMMANDS.keys())}"}

    # Login
    login_result = _https_post(ip, "/web_api/login", {"Content-Type": "application/json"},
                               {"user": user, "password": password})
    sid = None
    if isinstance(login_result.get("data"), dict):
        sid = login_result["data"].get("sid")
    if not sid:
        return {"error": "Login failed", "detail": login_result}

    headers = {"Content-Type": "application/json", "X-chkp-sid": sid}

    try:
        result = _https_post(ip, spec["path"], headers, spec.get("body", {}))
    finally:
        # Always logout
        try:
            _https_post(ip, "/web_api/logout", headers, {})
        except Exception:
            pass

    return result


def _exec_ssh(ip: str, env: dict[str, str], command: str) -> dict[str, Any]:
    """Execute an SSH command on a Cisco lab device using an interactive shell."""
    import paramiko  # type: ignore
    import time as _time

    user = env.get("SSH_USER", "admin")
    password = env.get("SSH_PASS", "Cisco123!")
    port = int(env.get("SSH_PORT", "22"))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(ip, port=port, username=user, password=password,
                       timeout=10, look_for_keys=False, allow_agent=False)

        # Use interactive shell (the mock expects PTY + shell, not exec)
        chan = client.invoke_shell(width=512, height=24)
        chan.settimeout(10.0)

        # Wait for initial prompt
        _time.sleep(0.5)
        initial = b""
        while chan.recv_ready():
            initial += chan.recv(4096)

        # Send command
        chan.sendall(f"{command}\n".encode())
        _time.sleep(1.0)

        # Collect output
        output = b""
        deadline = _time.time() + 5.0
        while _time.time() < deadline:
            if chan.recv_ready():
                chunk = chan.recv(8192)
                if not chunk:
                    break
                output += chunk
            else:
                _time.sleep(0.1)
                # If nothing for 0.5s after last data, we're done
                if not chan.recv_ready():
                    break

        # Close
        chan.sendall(b"exit\n")
        chan.close()

        text = output.decode("utf-8", errors="replace")
        # Strip the echoed command from the first line
        lines = text.split("\r\n")
        if lines and command in lines[0]:
            lines = lines[1:]
        text = "\n".join(line.rstrip("\r") for line in lines)

        return {"output": text.strip()}
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        client.close()


def _exec_juniper_netconf(ip: str, env: dict[str, str], command: str) -> dict[str, Any]:
    """Execute a NETCONF RPC on a Juniper lab device via raw SSH subsystem."""
    import paramiko  # type: ignore

    user = env.get("SSH_USER", "admin")
    password = env.get("SSH_PASS", "Juniper123!")
    port = int(env.get("SSH_PORT", "22"))

    # Map friendly commands to NETCONF RPCs
    JUNIPER_RPC_MAP: dict[str, str] = {
        "show version":       "<get-software-information/>",
        "show interfaces":    "<get-interface-information/>",
        "show vlans":         "<get-vlan-information/>",
        "show chassis":       "<get-chassis-inventory/>",
        "show system info":   "<get-system-information/>",
        "show config":        "<get-config><source><running/></source></get-config>",
        "show route":         "<get-route-information/>",
        "show mac table":     "<get-ethernet-switching-table-information/>",
    }

    rpc_body = JUNIPER_RPC_MAP.get(command)
    if not rpc_body:
        # Allow raw RPC XML
        if command.strip().startswith("<"):
            rpc_body = command.strip()
        else:
            return {"error": f"Unknown command. Available: {', '.join(JUNIPER_RPC_MAP.keys())}"}

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(ip, port=port, username=user, password=password,
                       timeout=10, look_for_keys=False, allow_agent=False)

        transport = client.get_transport()
        if not transport:
            return {"error": "Could not open transport"}

        chan = transport.open_session()
        chan.invoke_subsystem("netconf")
        chan.settimeout(10.0)

        # Read server hello
        hello_data = b""
        while True:
            chunk = chan.recv(4096)
            hello_data += chunk
            if b"]]>]]>" in hello_data:
                break

        # Send client hello
        client_hello = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">'
            '<capabilities>'
            '<capability>urn:ietf:params:netconf:base:1.0</capability>'
            '</capabilities>'
            '</hello>]]>]]>'
        )
        chan.sendall(client_hello.encode())

        # Send RPC
        rpc_msg = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="1">'
            f'{rpc_body}'
            f'</rpc>]]>]]>'
        )
        chan.sendall(rpc_msg.encode())

        # Read response
        resp_data = b""
        while True:
            chunk = chan.recv(8192)
            if not chunk:
                break
            resp_data += chunk
            if b"]]>]]>" in resp_data:
                break

        # Close
        close_msg = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="99">'
            '<close-session/>'
            '</rpc>]]>]]>'
        )
        chan.sendall(close_msg.encode())
        chan.close()

        reply_str = resp_data.decode("utf-8", errors="replace").split("]]>]]>")[0]

        # Parse XML to dict for readability
        try:
            root = ET.fromstring(reply_str)
            return {"data": _xml_to_dict(root)}
        except Exception:
            return {"output": reply_str}

    except Exception as exc:
        return {"error": str(exc)}
    finally:
        client.close()


def _xml_to_dict(element: ET.Element) -> Any:
    """Recursively convert an XML Element tree to a nested dict."""
    # Strip namespace
    tag = re.sub(r"\{[^}]+\}", "", element.tag)

    children = list(element)
    if not children:
        text = (element.text or "").strip()
        return {tag: text} if text else {tag: None}

    result: dict[str, Any] = {}
    for child in children:
        child_dict = _xml_to_dict(child)
        child_tag = list(child_dict.keys())[0]
        child_val = child_dict[child_tag]
        if child_tag in result:
            # If duplicate tags, convert to list
            existing = result[child_tag]
            if not isinstance(existing, list):
                result[child_tag] = [existing]
            result[child_tag].append(child_val)
        else:
            result[child_tag] = child_val

    return {tag: result}


EXEC_DISPATCH = {
    "fortinet": _exec_fortinet,
    "paloalto": _exec_paloalto,
    "checkpoint": _exec_checkpoint,
    "cisco-ios": _exec_ssh,
    "cisco-nxos": _exec_ssh,
    "cisco-router": _exec_ssh,
}


class ExecRequest(BaseModel):
    command: str


class ExecHelpEntry(BaseModel):
    command: str
    description: str


@router.post("/containers/{container_id}/exec")
async def exec_command(
    container_id: str,
    body: ExecRequest,
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    """Execute a query against a lab device.

    For API-based devices (Fortinet, Palo Alto, Check Point), translates
    friendly commands to REST/XML API calls.
    For SSH devices (Cisco), proxies the command over SSH.
    For NETCONF devices (Juniper), wraps the command as a NETCONF RPC.
    """
    client = _get_docker()
    c = _get_lab_container(client, container_id)

    if c.status != "running":
        raise HTTPException(status_code=409, detail="Container is not running")

    meta = _get_container_meta(c)
    type_id = meta["type_id"]
    ip = meta["ip"]
    env = meta["env"]

    if not ip:
        raise HTTPException(status_code=500, detail="Container has no IP address on the lab network")

    command = body.command.strip()

    # Handle "help" command universally
    if command.lower() in ("help", "?"):
        return _help_response(type_id)

    # Juniper uses NETCONF, not SSH exec
    if type_id == "juniper":
        return _exec_juniper_netconf(ip, env, command)

    handler = EXEC_DISPATCH.get(type_id)
    if not handler:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported device type for exec: {type_id!r}",
        )

    return handler(ip, env, command)


@router.get("/containers/{container_id}/exec/help")
async def exec_help(
    container_id: str,
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    """Return available commands for a lab device."""
    client = _get_docker()
    c = _get_lab_container(client, container_id)
    meta = _get_container_meta(c)
    return _help_response(meta["type_id"])


def _help_response(type_id: str) -> dict[str, Any]:
    """Build a help response listing available commands."""
    if type_id in COMMAND_REGISTRY:
        commands = list(COMMAND_REGISTRY[type_id].keys())
        return {
            "type": type_id,
            "protocol": "HTTPS API",
            "commands": commands,
            "hint": "Type any command above, or use raw API paths like 'GET /api/...'",
        }
    if type_id == "juniper":
        commands = [
            "show version", "show interfaces", "show vlans", "show chassis",
            "show system info", "show config", "show route", "show mac table",
        ]
        return {
            "type": type_id,
            "protocol": "NETCONF",
            "commands": commands,
            "hint": "Type any command above, or send raw NETCONF XML like '<get-software-information/>'",
        }
    if type_id in SSH_DEVICE_TYPES:
        commands = [
            "show version", "show interfaces", "show vlan brief", "show vlan",
            "show running-config", "show ip interface brief", "show ip arp",
            "show mac address-table", "show cdp neighbors",
        ]
        return {
            "type": type_id,
            "protocol": "SSH",
            "commands": commands,
            "hint": "Type any IOS/NX-OS show command.",
        }
    return {"type": type_id, "commands": [], "hint": "Unknown device type"}
