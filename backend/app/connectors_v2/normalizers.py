"""
Normaliseurs partagés pour les connecteurs V1 et V2.

Fonctions pures (pas de *self*) qui prennent des données brutes et retournent
des structures normalisées prêtes pour Neo4j.

Utilisation :
    from app.connectors_v2.normalizers import normalize_interfaces, safe_id, ...

    interfaces = normalize_interfaces(parsed_data, raw_output)
    device_id  = safe_id(serial)
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


# ── Helpers généraux ────────────────────────────────────────────────

def safe_id(value: str) -> str:
    """Nettoie une chaîne pour en faire un ID Neo4j valide.

    Remplace les ~18 implémentations redondantes de ``_safe_id()`` /
    ``_clean_identifier()`` présentes dans les connecteurs V1.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-")
    return cleaned or "unknown"


def hash_id(seed: str, prefix: str = "DEV") -> str:
    """Génère un ID stable à partir d'un *seed* (hostname, IP…)."""
    h = hashlib.md5(seed.encode()).hexdigest()[:8].upper()
    return f"{prefix}-{h}"


def is_ip_interface_brief_command(command: str) -> bool:
    """Détecte si une commande est ``show ip interface brief``."""
    return bool(
        re.search(
            r"\bshow\s+ip\s+int(?:erface)?\s+brief\b",
            command.strip().lower(),
        )
    )


# ── Extraction system info ──────────────────────────────────────────

def extract_system_info(output: str, result: dict[str, Any]) -> dict[str, Any]:
    """Extrait hostname, serial, model, os_version depuis un ``show version`` brut.

    Retourne une copie de *result* enrichie ; ne mute pas l'entrée.
    """
    r = dict(result)  # copie pour ne pas muter l'original
    if not r.get("hostname"):
        for pat in [
            r"(\S+)\s+uptime",
            r"hostname\s+(\S+)",
            r"System Name\s*\.+\s*(\S+)",
            r"Hostname\s*:\s*(\S+)",
        ]:
            m = re.search(pat, output, re.IGNORECASE)
            if m:
                r["hostname"] = m.group(1)
                break
    if not r.get("serial"):
        for pat in [r"Processor board ID\s+(\S+)", r"Serial\s*(?:Number)?\s*:\s*(\S+)"]:
            m = re.search(pat, output, re.IGNORECASE)
            if m:
                r["serial"] = m.group(1)
                break
    if not r.get("model"):
        m = re.search(
            r"Model\s*(?:number)?\s*:\s*(.+?)(?:\s+Version|\s*$)",
            output,
            re.IGNORECASE,
        )
        if m:
            r["model"] = m.group(1).strip()
    if not r.get("os_version"):
        m = re.search(r"Version\s+([\d.]+)", output, re.IGNORECASE)
        if m:
            r["os_version"] = m.group(1)
    return r


# ── Interfaces ─────────────────────────────────────────────────────

def parse_interfaces_raw(raw: str) -> list[dict[str, str]]:
    """Parse le format Cisco ``GigabitEthernet0/1 is up, line protocol is up…``."""
    interfaces: list[dict[str, str]] = []
    current: dict[str, str] = {}
    seen: set[str] = set()
    for line in raw.splitlines():
        m = re.match(
            r"^(\S+)\s+is\s+(up|down|administratively down)",
            line.strip(),
            re.IGNORECASE,
        )
        if m:
            if current.get("name") and current["name"] not in seen:
                interfaces.append(current)
                seen.add(current["name"])
            current = {
                "name": m.group(1),
                "status": m.group(2),
                "ip": "",
                "mask": "",
            }
            continue
        if current:
            for pat in [r"Internet address is (\S+)", r"inet\s+(\S+)"]:
                ipm = re.search(pat, line)
                if ipm:
                    parts = ipm.group(1).split("/")
                    current["ip"] = parts[0]
                    if len(parts) > 1:
                        current["mask"] = parts[1]
    if current.get("name") and current["name"] not in seen:
        interfaces.append(current)
    return interfaces


def normalize_interfaces(
    parsed: list[dict[str, str]],
    raw: str,
) -> list[dict[str, Any]]:
    """Normalise les interfaces depuis un parse TextFSM ou du brut."""
    if parsed and parsed[0].get("raw"):
        return parse_interfaces_raw(raw)

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for iface in parsed:
        name = iface.get("interface", iface.get("name", iface.get("intf", "")))
        if not name or name in seen:
            continue
        seen.add(name)
        entry: dict[str, Any] = {
            "name": name,
            "status": iface.get("status", iface.get("link", "unknown")),
            "ip": iface.get("ip_address", iface.get("ipaddr", iface.get("ip", ""))),
            "mask": iface.get("mask", iface.get("subnet", "")),
        }
        for metric_key in [
            "input_rate",
            "output_rate",
            "input_errors",
            "output_errors",
            "crc",
            "runts",
            "giants",
            "frame",
            "input_packets",
            "output_packets",
        ]:
            val = iface.get(metric_key, iface.get(metric_key.upper(), ""))
            if val not in (None, "", "0"):
                try:
                    entry[metric_key] = int(val)
                except (ValueError, TypeError):
                    entry[metric_key] = val
        normalized.append(entry)

    if not normalized:
        return parse_interfaces_raw(raw)
    return normalized


def merge_interfaces(
    existing: list[dict[str, str]],
    new_items: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Fusionne deux listes d'interfaces en dédupliquant par nom."""
    merged: dict[str, dict[str, str]] = {}
    for iface in [*existing, *new_items]:
        name = str(iface.get("name", "")).strip()
        if not name:
            continue
        current = merged.setdefault(
            name,
            {"name": name, "status": "unknown", "ip": "", "mask": ""},
        )
        status = str(iface.get("status", "")).strip()
        if status and status != "unknown":
            current["status"] = status
        for field in ("ip", "mask"):
            value = str(iface.get(field, "")).strip()
            if value:
                current[field] = value
    return list(merged.values())


def parse_ip_int_brief(
    raw: str,
    existing: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Parse ``show ip interface brief`` et fusionne avec les existantes."""
    seen = {i["name"] for i in existing}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] not in ("Interface",):
            m = re.match(r"(\S+)", parts[0])
            if m:
                name = m.group(1)
                ip = parts[1] if len(parts) > 1 and parts[1] != "unassigned" else ""
                status = "up" if len(parts) > 4 and "up" in parts[4].lower() else "down"
                if name not in seen and ip:
                    seen.add(name)
                    existing.append(
                        {"name": name, "status": status, "ip": ip, "mask": ""}
                    )
    return existing


# ── Routes ─────────────────────────────────────────────────────────

def normalize_routes(
    parsed: list[dict[str, str]],
    raw: str,
) -> list[dict[str, str]]:
    """Normalise les routes."""
    if parsed and parsed[0].get("raw"):
        routes: list[dict[str, str]] = []
        seen: set[str] = set()
        for line in raw.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+/\d+)", line)
            if m and m.group(1) not in seen:
                routes.append({"network": m.group(1)})
                seen.add(m.group(1))
        return routes
    return [
        {"network": r.get("network", r.get("prefix", ""))}
        for r in parsed
        if r.get("network") or r.get("prefix")
    ]


# ── VLANs ──────────────────────────────────────────────────────────

def normalize_vlans(
    parsed: list[dict[str, str]],
    raw: str,
) -> list[dict[str, Any]]:
    """Normalise les VLANs."""
    if parsed and parsed[0].get("raw"):
        vlans: list[dict[str, Any]] = []
        seen: set[str] = set()
        for line in raw.splitlines():
            m = re.match(r"^\s*(\d+)\s+(\S+)", line.strip())
            if m and m.group(1).isdigit() and m.group(1) not in seen:
                vlans.append(
                    {
                        "vlan_id": m.group(1),
                        "name": m.group(2),
                        "interfaces": [],
                    }
                )
                seen.add(m.group(1))
        return vlans

    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for v in parsed:
        vid = v.get("vlan_id", v.get("id", ""))
        if not vid or vid in seen_ids:
            continue
        seen_ids.add(vid)
        raw_ports = v.get("interfaces", v.get("ports", ""))
        ports: list[str] = []
        if isinstance(raw_ports, list):
            ports = [p.strip() for p in raw_ports if p.strip()]
        elif isinstance(raw_ports, str) and raw_ports.strip():
            ports = [
                x.strip()
                for x in raw_ports.replace(",", " ").split()
                if x.strip()
            ]
        result.append(
            {
                "vlan_id": vid,
                "name": v.get("name", v.get("vlan_name", "")),
                "interfaces": ports,
            }
        )
    return result


# ── BGP ────────────────────────────────────────────────────────────

def normalize_bgp(
    parsed: list[dict[str, str]],
    raw: str,
) -> list[dict[str, str]]:
    """Normalise les peers BGP."""
    if parsed and parsed[0].get("raw"):
        peers: list[dict[str, str]] = []
        seen: set[str] = set()
        for line in raw.splitlines():
            m = re.match(r"^(\d+\.\d+\.\d+\.\d+)\s+", line.strip())
            if m and m.group(1) not in seen:
                peers.append({"neighbor": m.group(1)})
                seen.add(m.group(1))
        return peers
    return [
        {"neighbor": p.get("neighbor", p.get("bgp_peer", ""))}
        for p in parsed
        if p.get("neighbor") or p.get("bgp_peer")
    ]


# ── Redondance (HSRP / VRRP / EtherChannel / Stack) ────────────────

def normalize_redundancy(
    parsed: list[dict],
    protocol: str,
    raw: str,
) -> dict[str, Any]:
    """Normalise HSRP/VRRP standby data."""
    result: dict[str, Any] = {
        "protocol": protocol,
        "groups": [],
        "has_redundancy": False,
    }
    if parsed and not parsed[0].get("raw"):
        for entry in parsed:
            group_id = entry.get("group", entry.get("grp_num", ""))
            virtual_ip = entry.get("virtual_ip", entry.get("ip", ""))
            state = entry.get("state", "").lower()
            priority = entry.get("priority", "")
            active_router = entry.get("active_router", "")
            standby_router = entry.get("standby_router", "")
            interface = entry.get("interface", entry.get("iface", ""))
            if group_id:
                result["groups"].append(
                    {
                        "group": group_id,
                        "virtual_ip": virtual_ip,
                        "state": state,
                        "priority": priority,
                        "active_router": active_router,
                        "standby_router": standby_router,
                        "interface": interface,
                    }
                )
                if (
                    state == "active"
                    and standby_router
                    and standby_router not in ("unknown", "this")
                ):
                    result["has_redundancy"] = True
    if not result["groups"]:
        for line in raw.splitlines():
            m = re.search(
                r"Group\s+(\d+).*state\s+(Active|Standby|Init|Listen)",
                line,
                re.IGNORECASE,
            )
            if m:
                result["groups"].append(
                    {"group": m.group(1), "state": m.group(2).lower()}
                )
                result["has_redundancy"] = True
    return result


def normalize_etherchannel(parsed: list[dict], raw: str) -> dict[str, Any]:
    """Normalise EtherChannel / port-channel data."""
    result: dict[str, Any] = {
        "protocol": "etherchannel",
        "channels": [],
        "has_redundancy": False,
    }
    if parsed and not parsed[0].get("raw"):
        for entry in parsed:
            channel = entry.get(
                "channel", entry.get("group", entry.get("port_channel", ""))
            )
            ports = entry.get("ports", entry.get("member_interfaces", ""))
            protocol = entry.get("protocol", entry.get("mode", ""))
            status = entry.get("status", entry.get("state", ""))
            if channel:
                result["channels"].append(
                    {
                        "channel": channel,
                        "ports": ports,
                        "protocol": protocol,
                        "status": status,
                    }
                )
                if len(ports.split(",")) if ports else 0 >= 2:
                    result["has_redundancy"] = True
    return result


def normalize_redundancy_general(
    parsed: list[dict],
    raw: str,
) -> dict[str, Any]:
    """Normalise ``show redundancy`` output."""
    result: dict[str, Any] = {
        "protocol": "redundancy",
        "has_redundancy": False,
        "details": {},
    }
    for line in raw.splitlines():
        m = re.search(
            r"System Redundancy Protocol\s*=\s*(\S+)", line, re.IGNORECASE
        )
        if m:
            result["details"]["protocol"] = m.group(1)
        m = re.search(r"Redundancy.*State\s*=\s*(\S+)", line, re.IGNORECASE)
        if m:
            result["details"]["state"] = m.group(1).lower()
            result["has_redundancy"] = m.group(1).lower() != "none"
    return result


# ── CDP / LLDP neighbors ──────────────────────────────────────────

def normalize_neighbors(parsed: list[dict], protocol: str) -> list[dict]:
    """Normalise les voisins CDP/LLDP."""
    neighbors: list[dict] = []
    for entry in parsed if isinstance(parsed, list) else []:
        if not entry.get("neighbor_name"):
            continue
        neighbors.append(
            {
                "hostname": entry.get("neighbor_name", ""),
                "local_interface": entry.get("local_interface", ""),
                "neighbor_interface": entry.get("neighbor_interface", ""),
                "platform": entry.get("platform", ""),
                "capabilities": entry.get("capabilities", ""),
                "management_ip": entry.get("mgmt_address", ""),
                "protocol": protocol,
            }
        )
    return neighbors


# ── ACL ────────────────────────────────────────────────────────────

def parse_acl_bindings(raw: str) -> list[dict[str, str]]:
    """Parse ``show ip interface`` pour extraire les bindings ACL par interface."""
    bindings: list[dict[str, str]] = []
    current_iface = ""
    for line in raw.splitlines():
        m = re.match(r"^(\S+)\s+is", line.strip())
        if m:
            current_iface = m.group(1)
        m_in = re.search(
            r"Inbound\s+access list\s+is\s+(.+)$", line, re.IGNORECASE
        )
        if m_in and current_iface:
            acl_name = m_in.group(1).strip()
            if acl_name.lower() != "not set":
                bindings.append(
                    {
                        "interface": current_iface,
                        "direction": "in",
                        "acl": acl_name,
                    }
                )
        m_out = re.search(
            r"Outgoing\s+access list\s+is\s+(.+)$", line, re.IGNORECASE
        )
        if m_out and current_iface:
            acl_name = m_out.group(1).strip()
            if acl_name.lower() != "not set":
                bindings.append(
                    {
                        "interface": current_iface,
                        "direction": "out",
                        "acl": acl_name,
                    }
                )
    return bindings


def normalize_access_lists(
    parsed: list[dict],
    raw: str,
) -> list[dict[str, Any]]:
    """Normalise ``show access-list`` output."""
    acls: list[dict[str, Any]] = []
    if parsed and not parsed[0].get("raw"):
        for entry in parsed:
            acl_id = entry.get("acl_id", entry.get("id", entry.get("number", "")))
            acl_name = entry.get("name", acl_id)
            acl_type = entry.get("type", "ip")
            entries = entry.get(
                "entries", entry.get("access_control_entries", [])
            )
            if acl_id:
                acls.append(
                    {
                        "id": acl_id,
                        "name": acl_name,
                        "type": acl_type,
                        "entries": entries,
                    }
                )
    if not acls:
        current_acl: dict[str, Any] | None = None
        for line in raw.splitlines():
            m = re.match(
                r"^(?:Standard|Extended)\s+IP\s+access\s+list\s+(.+)$",
                line,
                re.IGNORECASE,
            )
            if m:
                current_acl = {
                    "id": m.group(1).strip(),
                    "name": m.group(1).strip(),
                    "type": "ip",
                    "entries": [],
                }
                acls.append(current_acl)
            elif current_acl and line.strip() and not line.startswith(" "):
                current_acl = None
    return acls


# ── Services ───────────────────────────────────────────────────────

def normalize_http_service(raw: str, parsed: list[dict]) -> list[dict[str, Any]]:
    """Parse ``show ip http server status``."""
    enabled = False
    port = 80
    if parsed and not parsed[0].get("raw"):
        entry = parsed[0] if parsed else {}
        enabled = (
            entry.get("status", "").lower() == "enabled"
            if entry.get("status")
            else False
        )
        port = int(entry.get("port", 80)) if entry.get("port") else 80
    else:
        m = re.search(r"HTTP server status:\s*(\S+)", raw, re.IGNORECASE)
        if m:
            enabled = m.group(1).lower() == "enabled"
        m = re.search(r"HTTP server port:\s*(\d+)", raw, re.IGNORECASE)
        if m:
            port = int(m.group(1))
    return [
        {
            "name": "http",
            "protocol": "tcp",
            "port": port,
            "enabled": enabled,
            "source": "show ip http server status",
        }
    ]


# ── ARP ────────────────────────────────────────────────────────────

def normalize_arp(
    parsed: list[dict],
    raw: str,
) -> list[dict[str, Any]]:
    """Normalise les entrées ARP."""
    if parsed and not parsed[0].get("raw"):
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in parsed:
            ip = entry.get("address", entry.get("ip_address", entry.get("ip", "")))
            mac = entry.get("mac", entry.get("mac_address", ""))
            interface = entry.get("interface", entry.get("intf", ""))
            if ip and ip not in seen:
                seen.add(ip)
                result.append(
                    {
                        "ip": ip,
                        "mac": mac,
                        "interface": interface,
                        "type": entry.get("type", "dynamic"),
                    }
                )
        return result
    result = []
    seen = set()
    for line in raw.splitlines():
        m = re.match(
            r"^Internet\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", line, re.IGNORECASE
        )
        if m:
            ip = m.group(1)
            if ip not in seen:
                seen.add(ip)
                result.append(
                    {
                        "ip": ip,
                        "mac": m.group(3),
                        "interface": m.group(4),
                        "type": m.group(2).lower(),
                    }
                )
    return result


# ── FTD ────────────────────────────────────────────────────────────

def parse_ftd_network(output: str, result: dict[str, Any]) -> dict[str, Any]:
    """Parse ``show network`` FTD pour extraire hostname et interfaces."""
    r = dict(result)
    hm = re.search(r"Hostname\s*:\s*(\S+)", output, re.IGNORECASE)
    if hm:
        r["hostname"] = hm.group(1)
    iface_name: str | None = None
    for line in output.splitlines():
        m = re.match(r"=+\s*\[\s*(.+?)\s*]\s*=*\s*$", line)
        if m:
            iface_name = m.group(1).strip()
            continue
        if iface_name:
            im = re.match(r"Address\s*:\s*(\S+)", line)
            if im:
                ip = im.group(1)
                if ":" not in ip and ip.count(".") == 3:
                    r.setdefault("interfaces", []).append(
                        {
                            "name": iface_name,
                            "status": "up",
                            "ip": ip,
                            "mask": "",
                        }
                    )
    return r


# ── Push Neo4j (unifié) ────────────────────────────────────────────

async def push_to_neo4j(
    neo4j_client: Any,
    data: dict[str, Any],
    host: str,
    fingerprint: dict[str, Any],
) -> None:
    """Push normalisé dans Neo4j.

    Remplace ``_push_to_neo4j()`` du V2 et les implémentations
    redondantes des connecteurs V1.

    Paramètres
    ----------
    neo4j_client :
        Instance du client Neo4j (injectée).
    data :
        Données normalisées du sync.
    host :
        IP / hostname de l'équipement.
    fingerprint :
        Résultat du fingerprint (vendor, os, …).
    """
    hostname = data.get("hostname", host)
    serial = data.get("serial", hostname)
    device_id = f"DEV-{serial}"
    vendor = data.get("vendor", fingerprint.get("vendor", "unknown"))
    role = data.get("role", fingerprint.get("os", "unknown"))
    disp_name = f"{hostname} ({vendor}/{role})"

    try:
        existing = await _find_device(neo4j_client, hostname, host)
        if existing:
            device_id = existing["id"]

        redundancy = data.get("redundancy", {}) or {}
        has_red = (
            redundancy.get("has_redundancy", False)
            if isinstance(redundancy, dict)
            else False
        )
        red_proto = ""
        if isinstance(redundancy, dict):
            if redundancy.get("groups"):
                red_proto = f"hsrp_{len(redundancy['groups'])}_groups"
            elif redundancy.get("channels"):
                red_proto = (
                    f"etherchannel_{len(redundancy['channels'])}_channels"
                )
            elif redundancy.get("details", {}).get("protocol"):
                red_proto = redundancy["details"]["protocol"]
        elif redundancy:
            red_proto = "unknown"

        acl_bindings_json = json.dumps(data.get("acl_bindings", []))
        services_json = json.dumps(data.get("services", []))

        await neo4j_client.merge_node("Device", device_id, {
            "id": device_id,
            "type": role,
            "vendor": vendor,
            "hostname": hostname,
            "model": data.get("model", ""),
            "os_version": data.get("os_version", ""),
            "serial": serial,
            "ip": host,
            "role": role,
            "has_redundancy": has_red,
            "redundancy_protocol": red_proto,
            "acl_bindings": acl_bindings_json,
            "services": services_json,
            "display_name": disp_name,
        })
        data["device_id"] = device_id
        data["display_name"] = disp_name
    except Exception as e:
        data.setdefault("errors", []).append(f"neo4j device: {e}")

    await _push_interfaces(neo4j_client, data, serial, device_id, hostname)
    await _push_routes(neo4j_client, data, serial, device_id, hostname)
    await _push_vlans(neo4j_client, data, serial, device_id, hostname)
    await _push_neighbors(neo4j_client, data, device_id)
    await _push_arp(neo4j_client, data, serial, device_id, hostname)
    await _push_services(neo4j_client, data, serial, device_id, hostname)


async def _find_device(
    neo4j_client: Any,
    hostname: str,
    ip: str,
) -> dict[str, Any] | None:
    """Cherche un device existant par hostname+ip."""
    try:
        result = await neo4j_client.run_query(
            "MATCH (d:Device) WHERE d.hostname = $hostname AND d.ip = $ip "
            "RETURN d.id AS id LIMIT 1",
            {"hostname": hostname, "ip": ip},
        )
        if result:
            row = result[0]
            return {"id": row.get("d.id", row.get("id", ""))}
    except Exception:
        pass
    return None


async def _push_interfaces(
    neo4j_client: Any,
    data: dict[str, Any],
    serial: str,
    device_id: str,
    hostname: str,
) -> None:
    """Push les interfaces dans Neo4j."""
    vlan_ifaces: dict[str, list[str]] = {}
    for vlan in data.get("vlans", []):
        vid = vlan.get("vlan_id", "")
        ifaces = vlan.get("interfaces", [])
        if vid and ifaces:
            for ifname in ifaces:
                vlan_ifaces.setdefault(ifname, []).append(vid)

    acl_index: dict[str, dict[str, str]] = {}
    for b in data.get("acl_bindings", []):
        ifname = b.get("interface", "")
        direction = b.get("direction", "")
        acl_name = b.get("acl", "")
        if ifname:
            acl_index.setdefault(ifname, {})[direction] = acl_name

    seen = set()
    for iface in data.get("interfaces", []):
        ifname = iface.get("name", "")
        if not ifname or ifname in seen:
            continue
        seen.add(ifname)
        iface_id = f"IF-{serial}-{ifname}"
        acl_props: dict[str, str] = {}
        if ifname in acl_index:
            if "in" in acl_index[ifname]:
                acl_props["acl_in"] = acl_index[ifname]["in"]
            if "out" in acl_index[ifname]:
                acl_props["acl_out"] = acl_index[ifname]["out"]
        vlan_info: dict[str, str] = {}
        if ifname in vlan_ifaces:
            vlan_info["vlans"] = ",".join(vlan_ifaces[ifname])
        metrics: dict[str, int] = {}
        for m_key in [
            "input_rate",
            "output_rate",
            "input_errors",
            "output_errors",
            "crc",
            "runts",
            "giants",
            "frame",
        ]:
            val = iface.get(m_key)
            if val not in (None, "", 0):
                metrics[m_key] = (
                    int(val)
                    if isinstance(val, (int, float, str)) and str(val).isdigit()
                    else val
                )
        try:
            await neo4j_client.merge_node("Interface", iface_id, {
                "id": iface_id,
                "name": ifname,
                "status": iface.get("status", "unknown"),
                "ip": iface.get("ip", ""),
                "mask": iface.get("mask", ""),
                "display_name": f"{ifname} ({hostname})",
                **acl_props,
                **vlan_info,
                **metrics,
            })
            await neo4j_client.create_relationship(
                "Device", device_id, "HAS_INTERFACE", "Interface", iface_id
            )
        except Exception:
            pass


async def _push_routes(
    neo4j_client: Any,
    data: dict[str, Any],
    serial: str,
    device_id: str,
    hostname: str,
) -> None:
    """Push les routes dans Neo4j."""
    seen = set()
    for route in data.get("routes", []):
        network = route.get("network", "")
        if not network or network in seen:
            continue
        seen.add(network)
        safe_net = re.sub(r"[^A-Za-z0-9_-]", "_", network)
        route_id = f"ROUTE-{serial}-{safe_net}"
        try:
            await neo4j_client.merge_node("Route", route_id, {
                "id": route_id,
                "network": network,
                "display_name": f"Route {network} ({hostname})",
            })
            await neo4j_client.create_relationship(
                "Device", device_id, "HAS_ROUTE", "Route", route_id
            )
        except Exception:
            pass


async def _push_vlans(
    neo4j_client: Any,
    data: dict[str, Any],
    serial: str,
    device_id: str,
    hostname: str,
) -> None:
    """Push les VLANs dans Neo4j."""
    seen = set()
    for vlan in data.get("vlans", []):
        vid = vlan.get("vlan_id", "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        vlan_id_name = f"VLAN-{vid}-{serial}"
        try:
            await neo4j_client.merge_node("VLAN", vlan_id_name, {
                "id": vlan_id_name,
                "vlan_id": vid,
                "name": vlan.get("name", f"VLAN {vid}"),
                "display_name": f"VLAN {vid} ({hostname})",
            })
            await neo4j_client.create_relationship(
                "Device", device_id, "HAS_VLAN", "VLAN", vlan_id_name
            )
        except Exception:
            pass


async def _push_neighbors(
    neo4j_client: Any,
    data: dict[str, Any],
    device_id: str,
) -> None:
    """Push les voisins topologiques dans Neo4j."""
    for neighbor in data.get("topology_neighbors", []):
        nbr_host = neighbor.get("hostname", "")
        nbr_local_if = neighbor.get("local_interface", "")
        nbr_remote_if = neighbor.get("neighbor_interface", "")
        nbr_ip = neighbor.get("ip", "")
        if not nbr_host and not nbr_ip:
            continue
        try:
            found = None
            short_host = nbr_host.split(".")[0] if nbr_host else ""
            if nbr_host:
                found = await neo4j_client.run_query(
                    "MATCH (d:Device) WHERE d.hostname = $host "
                    "OR d.hostname = $short OR d.ip = $host "
                    "OR d.hostname CONTAINS $short RETURN d.id LIMIT 1",
                    {"host": nbr_host, "short": short_host},
                )
            if not found and nbr_ip:
                found = await neo4j_client.run_query(
                    "MATCH (d:Device) WHERE d.ip = $ip RETURN d.id LIMIT 1",
                    {"ip": nbr_ip},
                )
            if found:
                nbr_id = found[0]["d.id"]
                props: dict[str, str] = {
                    "source": neighbor.get("protocol", "cdp")
                }
                if nbr_local_if:
                    props["local_port"] = nbr_local_if
                if nbr_remote_if:
                    props["neighbor_port"] = nbr_remote_if
                await neo4j_client.create_relationship(
                    "Device",
                    device_id,
                    "CONNECTED_TO",
                    "Device",
                    nbr_id,
                    props,
                )
        except Exception:
            pass


async def _push_arp(
    neo4j_client: Any,
    data: dict[str, Any],
    serial: str,
    device_id: str,
    hostname: str,
) -> None:
    """Push les entrées ARP dans Neo4j."""
    for arp in data.get("arp_entries", []):
        arp_ip = arp.get("ip", "")
        arp_mac = arp.get("mac", "")
        arp_iface = arp.get("interface", "")
        if not arp_ip:
            continue
        arp_id = f"ARP-{serial}-{arp_ip.replace('.', '_')}"
        try:
            await neo4j_client.merge_node("ARP", arp_id, {
                "id": arp_id,
                "ip_address": arp_ip,
                "mac": arp_mac,
                "interface": arp_iface,
                "display_name": f"ARP {arp_ip} ({hostname})",
            })
            await neo4j_client.create_relationship(
                "Device", device_id, "HAS_ARP", "ARP", arp_id
            )
        except Exception:
            pass


async def _push_services(
    neo4j_client: Any,
    data: dict[str, Any],
    serial: str,
    device_id: str,
    hostname: str,
) -> None:
    """Push les services dans Neo4j."""
    for svc in data.get("services", []):
        svc_name = svc.get("name", "")
        svc_port = svc.get("port", "")
        svc_proto = svc.get("protocol", "")
        if not svc_name:
            continue
        svc_id = f"SVC-{serial}-{svc_name}-{svc_port}"
        try:
            await neo4j_client.merge_node("Service", svc_id, {
                "id": svc_id,
                "name": svc_name,
                "port": str(svc_port),
                "protocol": svc_proto,
                "enabled": svc.get("enabled", False),
                "display_name": f"{svc_name}:{svc_port} ({hostname})",
            })
            await neo4j_client.create_relationship(
                "Device", device_id, "RUNS", "Service", svc_id
            )
        except Exception:
            pass
