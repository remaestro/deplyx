#!/usr/bin/env python3
"""
Seed a medium-size enterprise topology for the **Datacenter Paris** site (site_id=2)
directly in Neo4j — no connectors, pure topology simulation.

Design goals:
- ~30 devices (core, dist, access, firewall, WAN, LB, WLC, servers)
- ~200 interfaces, ~80 VLANs, ~300 routes, ~50 firewall rules, ~40 services
- Realistic L2/L3 hierarchy with redundancy patterns
- Exercises all 8 relationship types + many properties
"""

from neo4j import GraphDatabase
import sys, os, re, hashlib, ipaddress

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD", "deplyxneo4j")

SITE_ID = 2  # Datacenter Paris

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

# ────────────────────────────────────────────────────────────────────
# 1.  Device definitions
# ────────────────────────────────────────────────────────────────────

DEVICES = {}

# Core (2x Nexus 9k VPC pair)
for i in [1, 2]:
    hostname = f"dc-par-core-0{i}"
    DEVICES[hostname] = {
        "vendor": "cisco", "role": "core_switch", "model": "Nexus-93180YC-FX",
        "os_version": "NX-OS 10.4(3)", "serial": f"FXS23{i:04d}AA",
        "mgmt_ip": f"10.100.0.{10 + i}", "redundancy_protocol": "vpc",
        "has_redundancy": True, "zone": "core",
    }

# Distribution (4x Catalyst 9500 HSRP pairs)
for i in [1, 2, 3, 4]:
    hostname = f"dc-par-dist-{i:02d}"
    DEVICES[hostname] = {
        "vendor": "cisco", "role": "dist_switch", "model": "C9500-48Y4C",
        "os_version": "IOS-XE 17.12.4", "serial": f"CAT95-D{i:02d}",
        "mgmt_ip": f"10.100.0.{20 + i}", "redundancy_protocol": "hsrp",
        "has_redundancy": True, "zone": "distribution",
    }

# Access (8x Catalyst 2960X / 9200L)
for i in range(1, 9):
    hostname = f"dc-par-acc-{i:02d}"
    model = "C2960X-48FPD-L" if i <= 4 else "C9200L-48P-4X"
    os_ver = "IOS 15.2(7)E9" if i <= 4 else "IOS-XE 17.9.5"
    DEVICES[hostname] = {
        "vendor": "cisco", "role": "access_switch", "model": model,
        "os_version": os_ver, "serial": f"CAT29-ACC{i:02d}",
        "mgmt_ip": f"10.100.0.{30 + i}", "zone": "access",
    }

# Firewalls (2x Fortinet HA)
for i in [1, 2]:
    hostname = f"dc-par-fw-0{i}"
    DEVICES[hostname] = {
        "vendor": "fortinet", "role": "firewall", "model": "FortiGate-600F",
        "os_version": "FortiOS 7.6.0", "serial": f"FG600-FW{i:02d}",
        "mgmt_ip": f"10.100.0.{40 + i}", "redundancy_protocol": "fgcp",
        "has_redundancy": True, "zone": "dmz",
    }

# WAN routers (2x ISR 4461)
for i in [1, 2]:
    hostname = f"dc-par-wan-{i:02d}"
    DEVICES[hostname] = {
        "vendor": "cisco", "role": "wan_router", "model": "ISR-4461",
        "os_version": "IOS-XE 17.12.4", "serial": f"ISR44-W{i:02d}",
        "mgmt_ip": f"10.100.0.{50 + i}", "redundancy_protocol": "bgp_multihome",
        "has_redundancy": True, "zone": "wan",
    }

# Load balancers (2x HAProxy)
for i in [1, 2]:
    hostname = f"dc-par-lb-0{i}"
    DEVICES[hostname] = {
        "vendor": "haproxy", "role": "load_balancer", "model": "HAProxy-Enterprise-2.9",
        "os_version": "2.9.5", "serial": f"LB-ENT-0{i}",
        "mgmt_ip": f"10.100.0.{60 + i}", "redundancy_protocol": "keepalived",
        "has_redundancy": True, "zone": "dmz",
    }

# WLCs (2x Cisco 9800-L)
for i in [1, 2]:
    hostname = f"dc-par-wlc-0{i}"
    DEVICES[hostname] = {
        "vendor": "cisco", "role": "wlc", "model": "C9800-L-F-K9",
        "os_version": "IOS-XE 17.12.4", "serial": f"WLC9800-0{i}",
        "mgmt_ip": f"10.100.0.{70 + i}", "redundancy_protocol": "nplus1",
        "has_redundancy": True, "zone": "wireless",
    }

# Servers (8)
SERVERS_LIST = [
    ("dc-par-srv-dns-01",   "dns",        "10.100.10.10", "mgmt"),
    ("dc-par-srv-dns-02",   "dns",        "10.100.10.11", "mgmt"),
    ("dc-par-srv-ntp-01",   "ntp",        "10.100.10.20", "mgmt"),
    ("dc-par-srv-ntp-02",   "ntp",        "10.100.10.21", "mgmt"),
    ("dc-par-srv-aaa-01",   "aaa",        "10.100.10.30", "mgmt"),
    ("dc-par-srv-syslog-01","syslog",     "10.100.10.40", "mgmt"),
    ("dc-par-srv-mon-01",   "monitoring", "10.100.10.50", "mgmt"),
    ("dc-par-srv-web-01",   "web",        "10.100.20.10", "dmz"),
    ("dc-par-srv-web-02",   "web",        "10.100.20.11", "dmz"),
    ("dc-par-srv-db-01",    "db",         "10.100.40.10", "db"),
    ("dc-par-srv-db-02",    "db",         "10.100.40.11", "db"),
    ("dc-par-srv-fs-01",    "fs",         "10.100.90.10", "storage"),
]
for hostname, srv_type, ip, zone in SERVERS_LIST:
    DEVICES[hostname] = {
        "vendor": "linux", "role": srv_type,
        "model": hostname.upper().replace("-", " "),
        "os_version": "Ubuntu 24.04 LTS",
        "serial": hashlib.md5(hostname.encode()).hexdigest()[:8].upper(),
        "mgmt_ip": ip, "zone": zone,
    }

# ISP peers (external, simulated)
DEVICES["isp-orange-biz"] = {
    "vendor": "orange", "role": "isp_peer", "model": "External",
    "os_version": "-", "serial": "ISP-ORA-001",
    "mgmt_ip": "192.0.2.1", "zone": "wan",
}
DEVICES["isp-sfr-pro"] = {
    "vendor": "sfr", "role": "isp_peer", "model": "External",
    "os_version": "-", "serial": "ISP-SFR-001",
    "mgmt_ip": "192.0.2.2", "zone": "wan",
}

# ────────────────────────────────────────────────────────────────────
# 2.  VLAN definitions per zone
# ────────────────────────────────────────────────────────────────────

VLAN_ZONES = {
    "mgmt":         (10, 19,  "10.100.10.0/24"),
    "prod_dmz":     (20, 29,  "10.100.20.0/24"),
    "prod_internal":(30, 39,  "10.100.30.0/24"),
    "prod_db":      (40, 49,  "10.100.40.0/24"),
    "guest_wifi":   (50, 59,  "10.100.50.0/24"),
    "corp_wifi":    (60, 69,  "10.100.60.0/24"),
    "voice":        (70, 79,  "10.100.70.0/24"),
    "iot":          (80, 89,  "10.100.80.0/24"),
    "storage":      (90, 99,  "10.100.90.0/24"),
    "backup":       (100, 109,"10.100.100.0/24"),
    "wan_transit":  (200, 209,"10.100.200.0/24"),
    "p2p":          (250, 255,"10.100.254.0/24"),
}

# ────────────────────────────────────────────────────────────────────
# 3.  Wiring (physical links)
# ────────────────────────────────────────────────────────────────────

CORE_DIST_LINKS = [
    ("dc-par-core-01", "dc-par-dist-01"), ("dc-par-core-01", "dc-par-dist-02"),
    ("dc-par-core-01", "dc-par-dist-03"), ("dc-par-core-01", "dc-par-dist-04"),
    ("dc-par-core-02", "dc-par-dist-01"), ("dc-par-core-02", "dc-par-dist-02"),
    ("dc-par-core-02", "dc-par-dist-03"), ("dc-par-core-02", "dc-par-dist-04"),
]

ACCESS_DIST_LINKS = [
    ("dc-par-acc-01", "dc-par-dist-01"), ("dc-par-acc-01", "dc-par-dist-02"),
    ("dc-par-acc-02", "dc-par-dist-01"), ("dc-par-acc-02", "dc-par-dist-02"),
    ("dc-par-acc-03", "dc-par-dist-01"), ("dc-par-acc-03", "dc-par-dist-02"),
    ("dc-par-acc-04", "dc-par-dist-01"), ("dc-par-acc-04", "dc-par-dist-02"),
    ("dc-par-acc-05", "dc-par-dist-03"), ("dc-par-acc-05", "dc-par-dist-04"),
    ("dc-par-acc-06", "dc-par-dist-03"), ("dc-par-acc-06", "dc-par-dist-04"),
    ("dc-par-acc-07", "dc-par-dist-03"), ("dc-par-acc-07", "dc-par-dist-04"),
    ("dc-par-acc-08", "dc-par-dist-03"), ("dc-par-acc-08", "dc-par-dist-04"),
]

CORE_FW_LINKS = [
    ("dc-par-core-01", "dc-par-fw-01"), ("dc-par-core-02", "dc-par-fw-02"),
    ("dc-par-fw-01", "dc-par-fw-02"),
]

FW_WAN_LINKS = [
    ("dc-par-fw-01", "dc-par-wan-01"), ("dc-par-fw-02", "dc-par-wan-02"),
]

ISP_PEERS = [
    ("dc-par-wan-01", "isp-orange-biz"), ("dc-par-wan-02", "isp-sfr-pro"),
]

LB_LINKS = [
    ("dc-par-lb-01", "dc-par-core-01"), ("dc-par-lb-02", "dc-par-core-02"),
]

WLC_LINKS = [
    ("dc-par-wlc-01", "dc-par-dist-01"), ("dc-par-wlc-02", "dc-par-dist-03"),
]

SERVER_ACCESS = {
    "dc-par-acc-01": ["dc-par-srv-dns-01", "dc-par-srv-ntp-01"],
    "dc-par-acc-02": ["dc-par-srv-dns-02", "dc-par-srv-ntp-02"],
    "dc-par-acc-03": ["dc-par-srv-aaa-01", "dc-par-srv-syslog-01"],
    "dc-par-acc-04": ["dc-par-srv-mon-01"],
    "dc-par-acc-05": ["dc-par-srv-web-01", "dc-par-srv-web-02"],
    "dc-par-acc-06": ["dc-par-srv-db-01"],
    "dc-par-acc-07": ["dc-par-srv-db-02"],
    "dc-par-acc-08": ["dc-par-srv-fs-01"],
}

# ────────────────────────────────────────────────────────────────────
# 4.  Services
# ────────────────────────────────────────────────────────────────────

SERVICES = [
    ("svc-dns-tcp",     "DNS (TCP)",      "tcp/53",   ["dc-par-srv-dns-01","dc-par-srv-dns-02"]),
    ("svc-dns-udp",     "DNS (UDP)",      "udp/53",   ["dc-par-srv-dns-01","dc-par-srv-dns-02"]),
    ("svc-ntp",         "NTP",            "udp/123",  ["dc-par-srv-ntp-01","dc-par-srv-ntp-02"]),
    ("svc-radius",      "RADIUS Auth",    "udp/1812", ["dc-par-srv-aaa-01"]),
    ("svc-tacacs",      "TACACS+",        "tcp/49",   ["dc-par-srv-aaa-01"]),
    ("svc-syslog-tcp",  "Syslog (TCP)",   "tcp/6514", ["dc-par-srv-syslog-01"]),
    ("svc-syslog-udp",  "Syslog (UDP)",   "udp/514",  ["dc-par-srv-syslog-01"]),
    ("svc-snmp",        "SNMP v3",        "udp/161",  ["dc-par-srv-mon-01"]),
    ("svc-netflow",     "NetFlow/IPFIX",  "udp/2055", ["dc-par-srv-mon-01"]),
    ("svc-grafana",     "Grafana",        "tcp/3000", ["dc-par-srv-mon-01"]),
    ("svc-prometheus",  "Prometheus",     "tcp/9090", ["dc-par-srv-mon-01"]),
    ("svc-https",       "HTTPS",          "tcp/443",  ["dc-par-srv-web-01","dc-par-srv-web-02"]),
    ("svc-http",        "HTTP",           "tcp/80",   ["dc-par-srv-web-01","dc-par-srv-web-02"]),
    ("svc-postgres",    "PostgreSQL",     "tcp/5432", ["dc-par-srv-db-01","dc-par-srv-db-02"]),
    ("svc-nfs",         "NFS",            "tcp/2049", ["dc-par-srv-fs-01"]),
    ("svc-ssh",         "SSH Admin",      "tcp/22",   ["dc-par-srv-dns-01","dc-par-srv-ntp-01","dc-par-srv-aaa-01","dc-par-srv-syslog-01","dc-par-srv-mon-01","dc-par-srv-web-01","dc-par-srv-db-01","dc-par-srv-fs-01"]),
    ("svc-dhcp",        "DHCP",           "udp/67",   ["dc-par-srv-dns-01"]),
    ("svc-ldap",        "LDAP",           "tcp/389",  ["dc-par-srv-aaa-01"]),
    ("svc-ldaps",       "LDAPS",          "tcp/636",  ["dc-par-srv-aaa-01"]),
    ("svc-k8s-api",     "K8s API",        "tcp/6443", ["dc-par-srv-web-01"]),
]

# ────────────────────────────────────────────────────────────────────
# 5.  Firewall rules
# ────────────────────────────────────────────────────────────────────

FW_RULES = [
    ("fw-rule-001", "Allow DNS from internal","permit","prod_internal","mgmt","10.100.30.0/24","10.100.10.10/32","udp/53",True),
    ("fw-rule-002", "Allow DNS from DMZ","permit","prod_dmz","mgmt","10.100.20.0/24","10.100.10.10/32","udp/53",True),
    ("fw-rule-003", "Allow NTP all zones","permit","any","mgmt","0.0.0.0/0","10.100.10.20/32","udp/123",False),
    ("fw-rule-004", "Allow HTTPS WAN→DMZ","permit","wan","dmz","0.0.0.0/0","10.100.20.0/24","tcp/443",True),
    ("fw-rule-005", "Allow HTTP WAN→DMZ","permit","wan","dmz","0.0.0.0/0","10.100.20.0/24","tcp/80",True),
    ("fw-rule-006", "Allow DB from internal","permit","prod_internal","db","10.100.30.0/24","10.100.40.0/24","tcp/5432",True),
    ("fw-rule-007", "Allow DB from web DMZ","permit","prod_dmz","db","10.100.20.0/24","10.100.40.0/24","tcp/5432",True),
    ("fw-rule-008", "Block guest→internal","deny","guest_wifi","prod_internal","0.0.0.0/0","10.100.30.0/24","any",True),
    ("fw-rule-009", "Block guest→DB","deny","guest_wifi","db","0.0.0.0/0","10.100.40.0/24","any",True),
    ("fw-rule-010", "Block guest→mgmt","deny","guest_wifi","mgmt","0.0.0.0/0","10.100.10.0/24","any",True),
    ("fw-rule-011", "Guest DHCP relay","permit","guest_wifi","mgmt","10.100.50.0/24","10.100.10.10/32","udp/67",False),
    ("fw-rule-012", "Allow corp WiFi→internal","permit","corp_wifi","prod_internal","10.100.60.0/24","10.100.30.0/24","any",True),
    ("fw-rule-013", "Allow corp WiFi→DB","permit","corp_wifi","db","10.100.60.0/24","10.100.40.0/24","tcp/5432",True),
    ("fw-rule-014", "Voice SIP trunk WAN","permit","voice","wan","10.100.70.0/24","0.0.0.0/0","udp/5060",True),
    ("fw-rule-015", "SNMP monitoring","permit","mgmt","all","10.100.10.50/32","0.0.0.0/0","udp/161",False),
    ("fw-rule-016", "Block IoT→internal","deny","iot","prod_internal","0.0.0.0/0","10.100.30.0/24","any",True),
    ("fw-rule-017", "IoT cloud only","permit","iot","wan","10.100.80.0/24","0.0.0.0/0","tcp/443",False),
    ("fw-rule-018", "Storage NFS internal","permit","prod_internal","storage","10.100.30.0/24","10.100.90.10/32","tcp/2049",True),
    ("fw-rule-019", "Backup from all","permit","any","backup","0.0.0.0/0","10.100.100.0/24","any",True),
    ("fw-rule-020", "SSH mgmt VLAN","permit","mgmt","all","10.100.10.0/24","0.0.0.0/0","tcp/22",True),
    ("fw-rule-021", "WAN ingress default deny","deny","wan","any","0.0.0.0/0","0.0.0.0/0","any",True),
    ("fw-rule-022", "RADIUS all zones","permit","any","mgmt","0.0.0.0/0","10.100.10.30/32","udp/1812",False),
    ("fw-rule-023", "TACACS+ mgmt","permit","mgmt","mgmt","10.100.10.0/24","10.100.10.30/32","tcp/49",False),
    ("fw-rule-024", "Syslog all devices","permit","any","mgmt","0.0.0.0/0","10.100.10.40/32","udp/514",False),
    ("fw-rule-025", "Block guest→corp WiFi","deny","guest_wifi","corp_wifi","0.0.0.0/0","10.100.60.0/24","any",True),
]

# ────────────────────────────────────────────────────────────────────
# 6.  Route generation
# ────────────────────────────────────────────────────────────────────

def generate_routes():
    routes = []
    # Default routes WAN → ISP
    routes.append(("ROUTE-DEFAULT-WAN01","0.0.0.0/0","isp-orange-biz","10.100.200.1","dc-par-wan-01"))
    routes.append(("ROUTE-DEFAULT-WAN02","0.0.0.0/0","isp-sfr-pro","10.100.200.2","dc-par-wan-02"))
    # FW → WAN
    routes.append(("ROUTE-DEFAULT-FW01","0.0.0.0/0","dc-par-wan-01","10.100.200.5","dc-par-fw-01"))
    routes.append(("ROUTE-DEFAULT-FW02","0.0.0.0/0","dc-par-wan-02","10.100.200.6","dc-par-fw-02"))
    # Core: routes to each VLAN subnet
    for zone_key, (vstart, vend, subnet) in VLAN_ZONES.items():
        if zone_key in ("wan_transit","p2p"):
            continue
        nh = f"10.100.254.{10 + vstart % 240}"
        for core_suffix in ["01","02"]:
            routes.append((f"ROUTE-CORE-{zone_key.upper()}-{core_suffix}", subnet,
                          f"dc-par-dist-0{(vstart % 4)+1}", nh, f"dc-par-core-{core_suffix}"))
    # Dist: default to core + routes to all VLANs
    for i in range(1,5):
        dist = f"dc-par-dist-{i:02d}"
        routes.append((f"ROUTE-DIST-DEFAULT-{i:02d}","0.0.0.0/0",
                       f"dc-par-core-0{(i%2)+1}", f"10.100.254.{20+i}", dist))
        for zone_key, (vstart, vend, subnet) in VLAN_ZONES.items():
            if zone_key in ("wan_transit","p2p"):
                continue
            routes.append((f"ROUTE-DIST{i:02d}-{zone_key.upper()}", subnet,
                          f"dc-par-core-0{(i%2)+1}", f"10.100.254.{30+vstart%200}", dist))
    # FW: routes to each internal subnet via core
    for fw_suffix in ["01","02"]:
        for zone_key, (vstart, vend, subnet) in VLAN_ZONES.items():
            if zone_key in ("wan_transit","p2p"):
                continue
            routes.append((f"ROUTE-FW{fw_suffix}-{zone_key.upper()}", subnet,
                          f"dc-par-core-{fw_suffix}", f"10.100.254.5{int(fw_suffix)}",
                          f"dc-par-fw-{fw_suffix}"))
    # Access: default to dist
    for i in range(1,9):
        routes.append((f"ROUTE-ACC-DEFAULT-{i:02d}","0.0.0.0/0",
                       f"dc-par-dist-{(i%4)+1:02d}", f"10.100.254.{100+i}",
                       f"dc-par-acc-{i:02d}"))
    # Servers: default to access switch
    for srv in [s for s in DEVICES if s.startswith("dc-par-srv-")]:
        idx = hash(srv) % 8 + 1
        acc = f"dc-par-acc-{idx:02d}"
        routes.append((f"ROUTE-{srv.replace('dc-par-','').upper()}-DEFAULT","0.0.0.0/0",
                       acc, f"10.100.10.{40+(hash(srv)%200)}", srv))
    return routes

# ────────────────────────────────────────────────────────────────────
# 7.  Execution
# ────────────────────────────────────────────────────────────────────

MERGE_NODE = """
MERGE (n:Device {id: $id}) SET n += $props, n.site_id = $site, n.last_seen = timestamp()
"""
MERGE_OTHER = """
MERGE (n:{label} {{id: $id}}) SET n += $props, n.site_id = $site, n.last_seen = timestamp()
"""

def run():
    with driver.session() as s:
        # 7a. Wipe site 2
        print("🧹 Cleaning site 2…")
        s.run("MATCH (n) WHERE n.site_id = $site DETACH DELETE n", site=SITE_ID)

        # 7b. Devices
        print(f"🖥️  Creating {len(DEVICES)} devices…")
        for hostname, props in DEVICES.items():
            device_id = f"DEV-{props['serial']}"
            device_props = {
                "id": device_id,
                "hostname": hostname,
                "display_name": f"{hostname} ({props.get('vendor','?')}/{props.get('role','?')})",
                "type": props.get("role", "unknown"),
                "vendor": props.get("vendor", "unknown"),
                "model": props.get("model", ""),
                "os_version": props.get("os_version", ""),
                "serial": props.get("serial", ""),
                "ip": props.get("mgmt_ip", ""),
                "role": props.get("role", "unknown"),
                "has_redundancy": props.get("has_redundancy", False),
                "redundancy_protocol": props.get("redundancy_protocol", ""),
                "zone": props.get("zone", ""),
            }
            s.run(MERGE_NODE, id=device_id, props=device_props, site=SITE_ID)

        # 7c. VLANs
        vlan_count = 0
        for zone_key, (vstart, vend, subnet) in VLAN_ZONES.items():
            for vid in range(vstart, vend + 1):
                vlan_id = f"VLAN-{vid}"
                s.run(MERGE_OTHER.format(label="VLAN"), id=vlan_id, props={
                    "id": vlan_id, "vlan_id": str(vid),
                    "name": f"VLAN {vid}",
                    "display_name": f"VLAN {vid} ({zone_key.replace('_',' ')})",
                    "subnet": subnet, "zone": zone_key,
                }, site=SITE_ID)
                vlan_count += 1
        print(f"  → {vlan_count} VLANs")

        # 7d. Interfaces
        iface_count = 0
        dev_serials = {h: p["serial"] for h, p in DEVICES.items()}
        for hostname, props in DEVICES.items():
            serial = props["serial"]
            role = props.get("role","")
            mgmt_ip = props.get("mgmt_ip","")
            zone = props.get("zone","")

            if role in ("core_switch","dist_switch"):
                ifaces = [("Gi1/0/1","1G","up"),("Gi1/0/2","1G","up"),("Gi1/0/3","1G","up"),
                         ("Gi1/0/4","1G","up"),("Te1/0/1","10G","up"),("Te1/0/2","10G","up"),
                         ("Lo0","Loopback","up"),("Mgmt0","Mgmt","up")]
                mgmt_iface = "Mgmt0"
            elif role == "access_switch":
                ifaces = [("Gi1/0/1","1G","up"),("Gi1/0/2","1G","up"),("Gi1/0/3","1G","up"),
                         ("Gi1/0/4","1G","up"),("Lo0","Loopback","up"),("Vlan1","SVI","up")]
                mgmt_iface = "Vlan1"
            elif role == "firewall":
                ifaces = [("port1","1G","up"),("port2","1G","up"),("port3","1G","up"),
                         ("port4","1G","up"),("port5","1G","up"),("port6","HA","up"),
                         ("mgmt","Mgmt","up")]
                mgmt_iface = "mgmt"
            elif role == "wan_router":
                ifaces = [("Gi0/0/0","1G","up"),("Gi0/0/1","1G","up"),("Gi0/0/2","1G","up"),
                         ("Lo0","Loopback","up"),("Mgmt0","Mgmt","up")]
                mgmt_iface = "Mgmt0"
            elif role in ("load_balancer","wlc"):
                ifaces = [("eth0","1G","up"),("eth1","1G","up"),("lo","Loopback","up")]
                mgmt_iface = "eth0"
            else:
                ifaces = [("eth0","1G","up"),("eth1","1G","up"),("lo","Loopback","up")]
                mgmt_iface = "eth0"

            for ifname, speed, status in ifaces:
                iface_id = f"IF-{serial}-{ifname.replace('/','-')}"
                iface_ip = mgmt_ip if ifname == mgmt_iface else ""
                s.run(MERGE_OTHER.format(label="Interface"), id=iface_id, props={
                    "id": iface_id, "name": ifname, "status": status, "speed": speed,
                    "ip": iface_ip, "mask": "", "display_name": f"{ifname} ({hostname})",
                    "zone": zone,
                }, site=SITE_ID)
                s.run("""
                MATCH (a:Device {id: $did}), (b:Interface {id: $iid})
                MERGE (a)-[r:HAS_INTERFACE]->(b) SET r.last_seen = timestamp()
                """, did=f"DEV-{serial}", iid=iface_id)
                iface_count += 1
        print(f"  → {iface_count} interfaces")

        # 7e. Physical wiring
        link_count = 0
        def wire(src, dst):
            nonlocal link_count
            sid = dev_serials.get(src) or hashlib.md5(src.encode()).hexdigest()[:8].upper()
            did = dev_serials.get(dst) or hashlib.md5(dst.encode()).hexdigest()[:8].upper()
            s.run("""
            MATCH (a:Device {id: $a}), (b:Device {id: $b})
            MERGE (a)-[r:CONNECTED_TO]->(b)
            SET r.id = $lid, r.site_id = $site, r.last_seen = timestamp()
            """, a=f"DEV-{sid}", b=f"DEV-{did}", lid=f"LINK-{sid}-{did}", site=SITE_ID)
            link_count += 1

        for src, dst in (CORE_DIST_LINKS + ACCESS_DIST_LINKS + CORE_FW_LINKS +
                          FW_WAN_LINKS + ISP_PEERS + LB_LINKS + WLC_LINKS):
            wire(src, dst)
        for acc, servers in SERVER_ACCESS.items():
            for srv in servers:
                wire(acc, srv)
        print(f"  → {link_count} physical links")

        # 7f. Services
        for svc_id, svc_name, svc_port, servers in SERVICES:
            s.run(MERGE_OTHER.format(label="Service"), id=svc_id, props={
                "id": svc_id, "name": svc_name, "port": svc_port,
                "display_name": f"{svc_name} ({svc_port})",
            }, site=SITE_ID)
            for srv in servers:
                srv_ser = dev_serials.get(srv)
                if srv_ser:
                    s.run("""
                    MATCH (a:Device {id: $did}), (b:Service {id: $sid})
                    MERGE (a)-[r:RUNS]->(b) SET r.last_seen = timestamp()
                    """, did=f"DEV-{srv_ser}", sid=svc_id)
        print(f"  → {len(SERVICES)} services")

        # 7g. Firewall rules
        fw_devs = [f"DEV-{dev_serials[f'dc-par-fw-0{i}']}" for i in [1,2]]
        for (rid, name, action, sz, dz, sip, dip, svc, log) in FW_RULES:
            s.run(MERGE_OTHER.format(label="Rule"), id=rid, props={
                "id": rid, "name": name, "action": action,
                "src_zone": sz, "dst_zone": dz, "src_ip": sip, "dst_ip": dip,
                "service": svc, "log": log,
                "display_name": f"[{action.upper()}] {name}",
            }, site=SITE_ID)
            for fwd in fw_devs:
                s.run("""
                MATCH (a:Device {id: $did}), (b:Rule {id: $rid})
                MERGE (a)-[r:HAS_RULE]->(b) SET r.last_seen = timestamp()
                """, did=fwd, rid=rid)
        print(f"  → {len(FW_RULES)} firewall rules (×2 firewalls)")

        # 7h. Routes
        routes = generate_routes()
        for (rid, net, nh_dev, nh_ip, dev_name) in routes:
            dser = dev_serials.get(dev_name)
            if not dser:
                continue
            s.run(MERGE_OTHER.format(label="Route"), id=rid, props={
                "id": rid, "network": net, "next_hop": nh_ip,
                "next_hop_device": nh_dev,
                "display_name": f"Route {net} → {nh_ip}",
            }, site=SITE_ID)
            s.run("""
            MATCH (a:Device {id: $did}), (b:Route {id: $rid})
            MERGE (a)-[r:HAS_ROUTE]->(b) SET r.last_seen = timestamp()
            """, did=f"DEV-{dser}", rid=rid)
        print(f"  → {len(routes)} routes")

        # 7i. ARP
        arp_count = 0
        dev_list = list(dev_serials.keys())
        for zone_key, (vstart, vend, subnet) in VLAN_ZONES.items():
            net = ipaddress.ip_network(subnet, strict=False)
            for ip_obj in list(net.hosts())[:15]:
                ip_str = str(ip_obj)
                mac = "02:42:" + ":".join(f"{(hash(ip_str)>>(8*i))&0xff:02x}" for i in range(4))
                arp_id = f"ARP-{ip_str.replace('.','-')}"
                s.run(MERGE_OTHER.format(label="ARP"), id=arp_id, props={
                    "id": arp_id, "ip": ip_str, "mac": mac,
                    "display_name": f"ARP {ip_str} → {mac}",
                }, site=SITE_ID)
                di = dev_list[hash(ip_str) % len(dev_list)]
                s.run("""
                MATCH (a:Device {id: $did}), (b:ARP {id: $aid})
                MERGE (a)-[r:HAS_ARP]->(b) SET r.last_seen = timestamp()
                """, did=f"DEV-{dev_serials[di]}", aid=arp_id)
                arp_count += 1
        print(f"  → {arp_count} ARP entries")

        # 7j. Summary
        print("\n═══════════════════════════════════════")
        print("  Datacenter Paris — seed DONE")
        print("═══════════════════════════════════════")
        for row in s.run(
            "MATCH (n) WHERE n.site_id=$s RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC",
            s=SITE_ID
        ):
            print(f"  {row['l']:20s} {row['c']:>5d}")

        total_n = s.run("MATCH (n) WHERE n.site_id=$s RETURN count(n) AS c", s=SITE_ID).single()["c"]
        total_r = s.run("MATCH (a)-[r]->(b) WHERE a.site_id=$s OR b.site_id=$s RETURN count(r) AS c", s=SITE_ID).single()["c"]
        print(f"  {'─' * 30}")
        print(f"  {'TOTAL nodes':20s} {total_n:>5d}")
        print(f"  {'TOTAL relations':20s} {total_r:>5d}")

if __name__ == "__main__":
    run()
    driver.close()
    print("\n✅ Refresh the topology view with site Datacenter Paris (site_id=2).")
