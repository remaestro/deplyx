"""Seed script: populates Neo4j with a realistic demo infrastructure topology."""

from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def seed_graph() -> dict[str, int]:
    """Clear existing data and populate a demo topology. Returns entity counts."""

    await neo4j_client.clear_all()
    counts: dict[str, int] = {}

    # ── Datacenters ────────────────────────────────────────────────────
    datacenters = [
        {"id": "DC1", "name": "Datacenter Paris", "location": "Paris, FR"},
        {"id": "DC2", "name": "Datacenter London", "location": "London, UK"},
    ]
    for dc in datacenters:
        await neo4j_client.merge_node("Datacenter", dc["id"], dc)
    counts["datacenters"] = len(datacenters)

    # ── Firewalls ──────────────────────────────────────────────────────
    firewalls = [
        {"id": "FW-DC1-01", "type": "firewall", "vendor": "paloalto", "hostname": "pa-fw-dc1-01", "location": "DC1", "criticality": "critical"},
        {"id": "FW-DC1-02", "type": "firewall", "vendor": "fortinet", "hostname": "fg-fw-dc1-02", "location": "DC1", "criticality": "critical"},
        {"id": "FW-DC2-01", "type": "firewall", "vendor": "paloalto", "hostname": "pa-fw-dc2-01", "location": "DC2", "criticality": "critical"},
        {"id": "FW-DC2-02", "type": "firewall", "vendor": "fortinet", "hostname": "fg-fw-dc2-02", "location": "DC2", "criticality": "high"},
    ]
    for fw in firewalls:
        await neo4j_client.merge_node("Device", fw["id"], fw)
        await neo4j_client.create_relationship("Device", fw["id"], "LOCATED_IN", "Datacenter", fw["location"])
    counts["firewalls"] = len(firewalls)

    # ── Switches ───────────────────────────────────────────────────────
    switches = [
        {"id": "SW-DC1-CORE", "type": "switch", "vendor": "cisco", "hostname": "cisco-core-dc1", "location": "DC1", "criticality": "critical"},
        {"id": "SW-DC1-ACC-01", "type": "switch", "vendor": "cisco", "hostname": "cisco-acc01-dc1", "location": "DC1", "criticality": "medium"},
        {"id": "SW-DC1-ACC-02", "type": "switch", "vendor": "cisco", "hostname": "cisco-acc02-dc1", "location": "DC1", "criticality": "medium"},
        {"id": "SW-DC2-CORE", "type": "switch", "vendor": "cisco", "hostname": "cisco-core-dc2", "location": "DC2", "criticality": "critical"},
        {"id": "SW-DC2-ACC-01", "type": "switch", "vendor": "cisco", "hostname": "cisco-acc01-dc2", "location": "DC2", "criticality": "medium"},
        {"id": "SW-DC2-ACC-02", "type": "switch", "vendor": "cisco", "hostname": "cisco-acc02-dc2", "location": "DC2", "criticality": "low"},
    ]
    for sw in switches:
        await neo4j_client.merge_node("Device", sw["id"], sw)
        await neo4j_client.create_relationship("Device", sw["id"], "LOCATED_IN", "Datacenter", sw["location"])
    counts["switches"] = len(switches)

    # ── Device connections ─────────────────────────────────────────────
    connections = [
        # DC1 core topology
        ("FW-DC1-01", "SW-DC1-CORE"),
        ("FW-DC1-02", "SW-DC1-CORE"),
        ("SW-DC1-CORE", "SW-DC1-ACC-01"),
        ("SW-DC1-CORE", "SW-DC1-ACC-02"),
        # DC2 core topology
        ("FW-DC2-01", "SW-DC2-CORE"),
        ("FW-DC2-02", "SW-DC2-CORE"),
        ("SW-DC2-CORE", "SW-DC2-ACC-01"),
        ("SW-DC2-CORE", "SW-DC2-ACC-02"),
        # Inter-DC link
        ("SW-DC1-CORE", "SW-DC2-CORE"),
    ]
    for src, dst in connections:
        await neo4j_client.create_relationship("Device", src, "CONNECTED_TO", "Device", dst)
    counts["connections"] = len(connections)

    # ── Interfaces ─────────────────────────────────────────────────────
    interfaces = [
        {"id": "IF-FW-DC1-01-eth0", "name": "eth0", "speed": "10G", "status": "up", "device_id": "FW-DC1-01"},
        {"id": "IF-FW-DC1-01-eth1", "name": "eth1", "speed": "10G", "status": "up", "device_id": "FW-DC1-01"},
        {"id": "IF-FW-DC1-02-eth0", "name": "eth0", "speed": "1G", "status": "up", "device_id": "FW-DC1-02"},
        {"id": "IF-SW-DC1-CORE-gi01", "name": "gi0/1", "speed": "10G", "status": "up", "device_id": "SW-DC1-CORE"},
        {"id": "IF-SW-DC1-CORE-gi02", "name": "gi0/2", "speed": "10G", "status": "up", "device_id": "SW-DC1-CORE"},
        {"id": "IF-SW-DC1-ACC-01-gi01", "name": "gi0/1", "speed": "1G", "status": "up", "device_id": "SW-DC1-ACC-01"},
        {"id": "IF-SW-DC2-CORE-gi01", "name": "gi0/1", "speed": "10G", "status": "up", "device_id": "SW-DC2-CORE"},
        {"id": "IF-SW-DC2-CORE-gi02", "name": "gi0/2", "speed": "10G", "status": "up", "device_id": "SW-DC2-CORE"},
        {"id": "IF-FW-DC2-01-eth0", "name": "eth0", "speed": "10G", "status": "up", "device_id": "FW-DC2-01"},
        {"id": "IF-FW-DC2-01-eth1", "name": "eth1", "speed": "10G", "status": "up", "device_id": "FW-DC2-01"},
        {"id": "IF-SW-DC2-ACC-01-gi01", "name": "gi0/1", "speed": "1G", "status": "up", "device_id": "SW-DC2-ACC-01"},
        {"id": "IF-SW-DC2-ACC-02-gi01", "name": "gi0/1", "speed": "1G", "status": "up", "device_id": "SW-DC2-ACC-02"},
    ]
    for iface in interfaces:
        await neo4j_client.merge_node("Interface", iface["id"], iface)
        await neo4j_client.create_relationship("Device", iface["device_id"], "HAS_INTERFACE", "Interface", iface["id"])
        await neo4j_client.create_relationship("Interface", iface["id"], "PART_OF", "Device", iface["device_id"])
    counts["interfaces"] = len(interfaces)

    # ── Ports ─────────────────────────────────────────────────────────
    ports = [
        {"id": "PORT-SW-DC1-CORE-01", "number": 1, "port_type": "ethernet", "status": "up", "device_id": "SW-DC1-CORE"},
        {"id": "PORT-SW-DC1-CORE-02", "number": 2, "port_type": "ethernet", "status": "up", "device_id": "SW-DC1-CORE"},
        {"id": "PORT-SW-DC2-CORE-01", "number": 1, "port_type": "ethernet", "status": "up", "device_id": "SW-DC2-CORE"},
        {"id": "PORT-FW-DC1-01-01", "number": 1, "port_type": "sfp+", "status": "up", "device_id": "FW-DC1-01"},
    ]
    for port in ports:
        await neo4j_client.merge_node("Port", port["id"], port)
        await neo4j_client.create_relationship("Port", port["id"], "PART_OF", "Device", port["device_id"])
    counts["ports"] = len(ports)

    # ── Cables ────────────────────────────────────────────────────────
    cables = [
        {"id": "CBL-DC1-CORE-LINK-01", "cable_type": "fiber", "from_device_id": "SW-DC1-CORE", "to_device_id": "SW-DC1-ACC-01"},
        {"id": "CBL-DC1-CORE-LINK-02", "cable_type": "fiber", "from_device_id": "SW-DC1-CORE", "to_device_id": "SW-DC1-ACC-02"},
        {"id": "CBL-INTERDC-CORE", "cable_type": "fiber", "from_device_id": "SW-DC1-CORE", "to_device_id": "SW-DC2-CORE"},
    ]
    for cable in cables:
        await neo4j_client.merge_node("Cable", cable["id"], cable)
        await neo4j_client.create_relationship("Cable", cable["id"], "CONNECTED_TO", "Device", cable["from_device_id"])
        await neo4j_client.create_relationship("Cable", cable["id"], "CONNECTED_TO", "Device", cable["to_device_id"])
    counts["cables"] = len(cables)

    # ── VLANs ──────────────────────────────────────────────────────────
    vlans = [
        {"id": "VLAN-10", "vlan_id": 10, "name": "Management", "description": "Management network"},
        {"id": "VLAN-20", "vlan_id": 20, "name": "Production", "description": "Production servers"},
        {"id": "VLAN-30", "vlan_id": 30, "name": "DMZ", "description": "DMZ segment"},
        {"id": "VLAN-40", "vlan_id": 40, "name": "Database", "description": "Database segment"},
        {"id": "VLAN-50", "vlan_id": 50, "name": "VPN", "description": "VPN clients"},
        {"id": "VLAN-60", "vlan_id": 60, "name": "Backup", "description": "Backup network"},
        {"id": "VLAN-100", "vlan_id": 100, "name": "InterDC", "description": "Inter-datacenter link"},
        {"id": "VLAN-200", "vlan_id": 200, "name": "Guest", "description": "Guest wifi"},
    ]
    for vlan in vlans:
        await neo4j_client.merge_node("VLAN", vlan["id"], vlan)
    # Assign VLANs to switches
    vlan_assignments = [
        ("SW-DC1-CORE", "VLAN-10"), ("SW-DC1-CORE", "VLAN-20"), ("SW-DC1-CORE", "VLAN-100"),
        ("SW-DC1-ACC-01", "VLAN-20"), ("SW-DC1-ACC-01", "VLAN-30"),
        ("SW-DC1-ACC-02", "VLAN-40"), ("SW-DC1-ACC-02", "VLAN-50"),
        ("SW-DC2-CORE", "VLAN-10"), ("SW-DC2-CORE", "VLAN-20"), ("SW-DC2-CORE", "VLAN-100"),
        ("SW-DC2-ACC-01", "VLAN-20"), ("SW-DC2-ACC-01", "VLAN-60"),
        ("SW-DC2-ACC-02", "VLAN-30"), ("SW-DC2-ACC-02", "VLAN-200"),
    ]
    for sw_id, vlan_id in vlan_assignments:
        await neo4j_client.create_relationship("Device", sw_id, "HOSTS", "VLAN", vlan_id)
    counts["vlans"] = len(vlans)

    # ── IPs ────────────────────────────────────────────────────────────
    ips = [
        {"id": "IP-10.1.1.1", "address": "10.1.1.1", "subnet": "10.1.1.0/24", "version": 4},
        {"id": "IP-10.1.1.2", "address": "10.1.1.2", "subnet": "10.1.1.0/24", "version": 4},
        {"id": "IP-10.1.2.1", "address": "10.1.2.1", "subnet": "10.1.2.0/24", "version": 4},
        {"id": "IP-10.1.2.10", "address": "10.1.2.10", "subnet": "10.1.2.0/24", "version": 4},
        {"id": "IP-10.1.3.1", "address": "10.1.3.1", "subnet": "10.1.3.0/24", "version": 4},
        {"id": "IP-10.2.1.1", "address": "10.2.1.1", "subnet": "10.2.1.0/24", "version": 4},
        {"id": "IP-10.2.1.2", "address": "10.2.1.2", "subnet": "10.2.1.0/24", "version": 4},
        {"id": "IP-10.2.2.1", "address": "10.2.2.1", "subnet": "10.2.2.0/24", "version": 4},
        {"id": "IP-172.16.0.1", "address": "172.16.0.1", "subnet": "172.16.0.0/24", "version": 4},
        {"id": "IP-172.16.0.2", "address": "172.16.0.2", "subnet": "172.16.0.0/24", "version": 4},
        {"id": "IP-192.168.1.1", "address": "192.168.1.1", "subnet": "192.168.1.0/24", "version": 4},
        {"id": "IP-192.168.1.10", "address": "192.168.1.10", "subnet": "192.168.1.0/24", "version": 4},
        {"id": "IP-192.168.2.1", "address": "192.168.2.1", "subnet": "192.168.2.0/24", "version": 4},
        {"id": "IP-192.168.2.5", "address": "192.168.2.5", "subnet": "192.168.2.0/24", "version": 4},
        {"id": "IP-10.0.100.1", "address": "10.0.100.1", "subnet": "10.0.100.0/24", "version": 4},
        {"id": "IP-10.0.100.2", "address": "10.0.100.2", "subnet": "10.0.100.0/24", "version": 4},
        {"id": "IP-10.0.200.1", "address": "10.0.200.1", "subnet": "10.0.200.0/24", "version": 4},
        {"id": "IP-10.0.200.5", "address": "10.0.200.5", "subnet": "10.0.200.0/24", "version": 4},
        {"id": "IP-10.0.50.1", "address": "10.0.50.1", "subnet": "10.0.50.0/24", "version": 4},
        {"id": "IP-10.0.50.10", "address": "10.0.50.10", "subnet": "10.0.50.0/24", "version": 4},
    ]
    for ip in ips:
        await neo4j_client.merge_node("IP", ip["id"], ip)
    # Assign IPs to interfaces
    ip_iface_map = [
        ("IF-FW-DC1-01-eth0", "IP-10.1.1.1"),
        ("IF-FW-DC1-01-eth1", "IP-172.16.0.1"),
        ("IF-FW-DC1-02-eth0", "IP-10.1.1.2"),
        ("IF-SW-DC1-CORE-gi01", "IP-10.1.2.1"),
        ("IF-SW-DC1-ACC-01-gi01", "IP-10.1.3.1"),
        ("IF-FW-DC2-01-eth0", "IP-10.2.1.1"),
        ("IF-FW-DC2-01-eth1", "IP-172.16.0.2"),
        ("IF-SW-DC2-CORE-gi01", "IP-10.2.2.1"),
    ]
    for iface_id, ip_id in ip_iface_map:
        await neo4j_client.create_relationship("Interface", iface_id, "HAS_IP", "IP", ip_id)
    counts["ips"] = len(ips)

    # ── Applications ───────────────────────────────────────────────────
    apps = [
        {"id": "APP-WEB", "name": "WebApp", "description": "Customer-facing web application", "criticality": "critical", "owner": "Platform Team"},
        {"id": "APP-DB", "name": "Database", "description": "PostgreSQL cluster", "criticality": "critical", "owner": "DBA Team"},
        {"id": "APP-MAIL", "name": "Mail Server", "description": "Corporate email system", "criticality": "high", "owner": "IT Ops"},
        {"id": "APP-DNS", "name": "DNS", "description": "Internal DNS resolver", "criticality": "critical", "owner": "Network Team"},
        {"id": "APP-VPN", "name": "VPN Gateway", "description": "Remote access VPN", "criticality": "high", "owner": "Security Team"},
    ]
    for app in apps:
        await neo4j_client.merge_node("Application", app["id"], app)
    counts["applications"] = len(apps)

    # ── Services ───────────────────────────────────────────────────────
    services = [
        {"id": "SVC-HTTP", "name": "HTTP", "port": 80, "protocol": "tcp"},
        {"id": "SVC-HTTPS", "name": "HTTPS", "port": 443, "protocol": "tcp"},
        {"id": "SVC-SMTP", "name": "SMTP", "port": 25, "protocol": "tcp"},
        {"id": "SVC-DNS", "name": "DNS", "port": 53, "protocol": "udp"},
        {"id": "SVC-PGSQL", "name": "PostgreSQL", "port": 5432, "protocol": "tcp"},
        {"id": "SVC-SSH", "name": "SSH", "port": 22, "protocol": "tcp"},
        {"id": "SVC-IPSEC", "name": "IPSec", "port": 500, "protocol": "udp"},
        {"id": "SVC-OPENVPN", "name": "OpenVPN", "port": 1194, "protocol": "udp"},
    ]
    for svc in services:
        await neo4j_client.merge_node("Service", svc["id"], svc)
    # Map services to applications
    svc_app_map = [
        ("APP-WEB", "SVC-HTTP"), ("APP-WEB", "SVC-HTTPS"),
        ("APP-DB", "SVC-PGSQL"),
        ("APP-MAIL", "SVC-SMTP"),
        ("APP-DNS", "SVC-DNS"),
        ("APP-VPN", "SVC-IPSEC"), ("APP-VPN", "SVC-OPENVPN"),
    ]
    for app_id, svc_id in svc_app_map:
        await neo4j_client.create_relationship("Application", app_id, "USES", "Service", svc_id)
    counts["services"] = len(services)

    # ── App → Device dependencies (DEPENDS_ON / hosting) ───────────────
    app_device_deps = [
        ("APP-WEB", "SW-DC1-ACC-01", "DEPENDS_ON"),
        ("APP-WEB", "FW-DC1-01", "DEPENDS_ON"),
        ("APP-DB", "SW-DC1-ACC-02", "DEPENDS_ON"),
        ("APP-MAIL", "SW-DC2-ACC-01", "DEPENDS_ON"),
        ("APP-DNS", "SW-DC1-CORE", "DEPENDS_ON"),
        ("APP-DNS", "SW-DC2-CORE", "DEPENDS_ON"),
        ("APP-VPN", "FW-DC1-01", "DEPENDS_ON"),
        ("APP-VPN", "FW-DC2-01", "DEPENDS_ON"),
    ]
    for app_id, dev_id, rel in app_device_deps:
        await neo4j_client.create_relationship("Application", app_id, rel, "Device", dev_id)

    # ── Firewall Rules ─────────────────────────────────────────────────
    rules = [
        {"id": "RULE-DC1-01", "name": "Allow HTTP to WebApp", "source": "any", "destination": "10.1.3.0/24", "port": "80", "protocol": "tcp", "action": "allow", "device_id": "FW-DC1-01"},
        {"id": "RULE-DC1-02", "name": "Allow HTTPS to WebApp", "source": "any", "destination": "10.1.3.0/24", "port": "443", "protocol": "tcp", "action": "allow", "device_id": "FW-DC1-01"},
        {"id": "RULE-DC1-03", "name": "Allow DB from WebApp", "source": "10.1.3.0/24", "destination": "10.1.2.0/24", "port": "5432", "protocol": "tcp", "action": "allow", "device_id": "FW-DC1-01"},
        {"id": "RULE-DC1-04", "name": "Deny DB from DMZ", "source": "192.168.1.0/24", "destination": "10.1.2.0/24", "port": "5432", "protocol": "tcp", "action": "deny", "device_id": "FW-DC1-01"},
        {"id": "RULE-DC1-05", "name": "Allow DNS", "source": "any", "destination": "10.1.2.1", "port": "53", "protocol": "udp", "action": "allow", "device_id": "FW-DC1-01"},
        {"id": "RULE-DC1-06", "name": "Allow VPN IPSec", "source": "any", "destination": "172.16.0.1", "port": "500", "protocol": "udp", "action": "allow", "device_id": "FW-DC1-01"},
        {"id": "RULE-DC1-07", "name": "Allow SSH management", "source": "10.1.1.0/24", "destination": "any", "port": "22", "protocol": "tcp", "action": "allow", "device_id": "FW-DC1-02"},
        {"id": "RULE-DC1-08", "name": "Allow InterDC", "source": "10.1.0.0/16", "destination": "10.2.0.0/16", "port": "any", "protocol": "any", "action": "allow", "device_id": "FW-DC1-02"},
        {"id": "RULE-DC2-01", "name": "Allow HTTP DC2", "source": "any", "destination": "10.2.1.0/24", "port": "80", "protocol": "tcp", "action": "allow", "device_id": "FW-DC2-01"},
        {"id": "RULE-DC2-02", "name": "Allow SMTP", "source": "any", "destination": "10.2.2.0/24", "port": "25", "protocol": "tcp", "action": "allow", "device_id": "FW-DC2-01"},
        {"id": "RULE-DC2-03", "name": "Allow VPN DC2", "source": "any", "destination": "172.16.0.2", "port": "500", "protocol": "udp", "action": "allow", "device_id": "FW-DC2-01"},
        {"id": "RULE-DC2-04", "name": "Deny ALL from Guest", "source": "10.0.200.0/24", "destination": "10.0.0.0/8", "port": "any", "protocol": "any", "action": "deny", "device_id": "FW-DC2-02"},
        {"id": "RULE-DC2-05", "name": "Allow Guest Internet", "source": "10.0.200.0/24", "destination": "0.0.0.0/0", "port": "443", "protocol": "tcp", "action": "allow", "device_id": "FW-DC2-02"},
        # Dangerous rule for policy engine to flag
        {"id": "RULE-DC2-06", "name": "LEGACY any-any", "source": "any", "destination": "any", "port": "any", "protocol": "any", "action": "allow", "device_id": "FW-DC2-02"},
        {"id": "RULE-DC1-09", "name": "Allow Backup traffic", "source": "10.1.0.0/16", "destination": "10.2.0.0/16", "port": "873", "protocol": "tcp", "action": "allow", "device_id": "FW-DC1-02"},
    ]
    for rule in rules:
        await neo4j_client.merge_node("Rule", rule["id"], rule)
        await neo4j_client.create_relationship("Device", rule["device_id"], "HAS_RULE", "Rule", rule["id"])
    counts["rules"] = len(rules)

    # Rules PROTECTS applications
    rule_app_protect = [
        ("RULE-DC1-01", "APP-WEB"), ("RULE-DC1-02", "APP-WEB"),
        ("RULE-DC1-03", "APP-DB"),
        ("RULE-DC1-04", "APP-DB"),
        ("RULE-DC1-05", "APP-DNS"),
        ("RULE-DC1-06", "APP-VPN"),
        ("RULE-DC2-02", "APP-MAIL"),
        ("RULE-DC2-03", "APP-VPN"),
    ]
    for rule_id, app_id in rule_app_protect:
        await neo4j_client.create_relationship("Rule", rule_id, "PROTECTS", "Application", app_id)

    # ── VLAN → Application ROUTES_TO ───────────────────────────────────
    vlan_routing = [
        ("VLAN-20", "APP-WEB"), ("VLAN-20", "APP-DB"),
        ("VLAN-30", "APP-WEB"),
        ("VLAN-40", "APP-DB"),
        ("VLAN-50", "APP-VPN"),
    ]
    for vlan_id, app_id in vlan_routing:
        await neo4j_client.create_relationship("VLAN", vlan_id, "ROUTES_TO", "Application", app_id)

    logger.info("Seed data loaded: %s", counts)
    return counts
