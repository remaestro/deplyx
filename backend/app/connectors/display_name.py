"""Display-name builder helpers.

``id`` and ``display_name`` are two distinct things.  ``id`` is the stable
internal key — never modified, never shown to the user.  ``display_name`` is
the human-readable label surfaced in the UI, dropdowns, topology views and
impact-analysis results.

Vendor and function strings must **always** be imported from here; inline
string literals in connector code are forbidden (verified by structural test).
"""

from typing import Final

# ── Vendor constants ──────────────────────────────────────────────────

VENDOR_FORTINET: Final[str] = "Fortinet"
VENDOR_PALO_ALTO: Final[str] = "Palo Alto"
VENDOR_CHECK_POINT: Final[str] = "Check Point"
VENDOR_CISCO: Final[str] = "Cisco"
VENDOR_JUNIPER: Final[str] = "Juniper"
VENDOR_ARUBA: Final[str] = "Aruba"
VENDOR_VYOS: Final[str] = "VyOS"
VENDOR_STRONGSWAN: Final[str] = "StrongSwan"
VENDOR_SNORT: Final[str] = "Snort"
VENDOR_OPENLDAP: Final[str] = "OpenLDAP"
VENDOR_NGINX: Final[str] = "Nginx"
VENDOR_POSTGRES: Final[str] = "PostgreSQL"
VENDOR_REDIS: Final[str] = "Redis"
VENDOR_ELASTICSEARCH: Final[str] = "Elasticsearch"
VENDOR_GRAFANA: Final[str] = "Grafana"
VENDOR_PROMETHEUS: Final[str] = "Prometheus"

# ── Function constants ────────────────────────────────────────────────

FUNCTION_FIREWALL: Final[str] = "Firewall"
FUNCTION_MANAGER: Final[str] = "Manager"
FUNCTION_GATEWAY: Final[str] = "Gateway"
FUNCTION_SWITCH: Final[str] = "Switch"
FUNCTION_ROUTER: Final[str] = "Router"
FUNCTION_WLC: Final[str] = "Wireless Controller"
FUNCTION_AP: Final[str] = "Access Point"
FUNCTION_VPN: Final[str] = "VPN Gateway"
FUNCTION_IDS: Final[str] = "IDS"
FUNCTION_DIRECTORY: Final[str] = "Directory"
FUNCTION_PROXY: Final[str] = "Reverse Proxy"
FUNCTION_DATABASE: Final[str] = "Database"
FUNCTION_CACHE: Final[str] = "Cache"
FUNCTION_SEARCH: Final[str] = "Search"
FUNCTION_MONITORING: Final[str] = "Monitoring"
FUNCTION_METRICS: Final[str] = "Metrics"


# ── Builder helpers ───────────────────────────────────────────────────


def device(vendor: str, function: str, hostname: str) -> str:
    """``Fortinet Firewall — fw-dc1-01`` (em-dash U+2014)."""
    return f"{vendor} {function} \u2014 {hostname}"


def interface(if_name: str, parent_display: str) -> str:
    """``port1  (Fortinet Firewall — fw-dc1-01)``."""
    return f"{if_name}  ({parent_display})"


def rule(rule_id: str | int, parent_display: str) -> str:
    """``Rule 42  (Fortinet Firewall — fw-dc1-01)``."""
    return f"Rule {rule_id}  ({parent_display})"


def vlan(vlan_id: int | str) -> str:
    """``VLAN 100``."""
    return f"VLAN {vlan_id}"


def ip_address(address: str) -> str:
    """``IP 192.168.1.1``."""
    return f"IP {address}"


def application(raw_name: str) -> str:
    """Replace hyphens/underscores with spaces for readability."""
    return raw_name.replace("-", " ").replace("_", " ")
