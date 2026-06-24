"""Collecteur de documentation pour la génération de profils YAML.

Va chercher les informations disponibles dans :
  - Netmiko (device_type supportés)
  - ntc-templates (templates TextFSM disponibles)
  - Profils Deplyx existants (pour servir de ``few-shot``)
  - LibreNMS OS list (via cache local ou web)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from app.utils.logging import get_logger

logger = get_logger(__name__)

# ── Chemins ─────────────────────────────────────────────────────────

_PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"

# Cache pour ne pas rescanner à chaque appel
_NETMIKO_DEVICE_TYPES: list[str] | None = None
_NTC_TEMPLATES_INDEX: dict[str, list[str]] | None = None

# ── Constantes Netmiko ──────────────────────────────────────────────

# Mapping constructeur → device_type Netmiko courants
# Basé sur https://github.com/netmiko/netmiko
NETMIKO_DEVICE_MAP: dict[str, list[str]] = {
    "cisco": [
        "cisco_ios", "cisco_ios_telnet", "cisco_xr", "cisco_nxos",
        "cisco_asa", "cisco_ftd", "cisco_ftd_ssh",
    ],
    "juniper": ["juniper_junos", "juniper_junos_telnet"],
    "fortinet": ["fortinet", "fortinet_ssh"],
    "paloalto": ["paloalto_panos", "paloalto_panos_ssh"],
    "arista": ["arista_eos", "arista_eos_telnet"],
    "huawei": ["huawei", "huawei_vrpv8", "huawei_olt"],
    "hp": ["hp_procurve", "hp_comware"],
    "aruba": ["aruba_os", "aruba_procurve"],
    "dell": ["dell_force10", "dell_powerconnect", "dell_os10", "dell_os9"],
    "extreme": ["extreme_exos", "extreme_netiron", "extreme_vsp", "extreme_wing"],
    "checkpoint": ["checkpoint_gaia"],
    "vyos": ["vyos"],
    "linux": ["linux"],
    "alcatel": ["alcatel_sros", "alcatel_aos"],
    "zyxel": ["zyxel_gs1900"],
    "adtran": ["adtran_os"],
}


def collect_device_info(
    vendor: str,
    os_name: str | None = None,
) -> dict[str, Any]:
    """Collecte toutes les infos disponibles pour un constructeur/OS.

    Paramètres
    ----------
    vendor :
        Nom du constructeur (ex: ``cisco``, ``fortinet``).
    os_name :
        Nom de l'OS (ex: ``ios``, ``fortios``). Si None, prend le premier.

    Retourne
    --------
    dict avec les clés :
        - vendor, os, device_types_netmiko, commands_textfsm,
          profiles_existants (few-shot), fallback
    """
    result: dict[str, Any] = {
        "vendor": vendor,
        "os": os_name,
        "device_types_netmiko": [],
        "commands_disponibles": [],
        "commands_avec_template": [],
        "commands_sans_template": [],
        "profiles_existants": [],
        "fallback_device_type": None,
    }

    # 1. Device types Netmiko
    result["device_types_netmiko"] = _get_netmiko_device_types(vendor, os_name)

    # 2. Templates TextFSM (ntc-templates)
    result["commands_avec_template"] = _get_textfsm_commands(vendor, os_name)
    result["commands_sans_template"] = _guess_common_commands(vendor, os_name)

    # 3. Profils existants (few-shot)
    result["profiles_existants"] = _get_existing_profiles(vendor, os_name)

    # 4. Fallback
    result["fallback_device_type"] = result["device_types_netmiko"][0] if result["device_types_netmiko"] else None

    # Toutes les commandes disponibles
    all_cmds = list(result["commands_avec_template"])
    all_cmds.extend(
        c for c in result["commands_sans_template"] if c not in all_cmds
    )
    result["commands_disponibles"] = all_cmds

    return result


# ── Netmiko ─────────────────────────────────────────────────────────

def _get_netmiko_device_types(
    vendor: str,
    os_name: str | None = None,
) -> list[str]:
    """Retourne les device_type Netmiko disponibles pour ce constructeur."""
    vendor_lower = vendor.lower().strip()

    # Vérifier le mapping statique
    if vendor_lower in NETMIKO_DEVICE_MAP:
        types = NETMIKO_DEVICE_MAP[vendor_lower]
        if os_name:
            # Filtrer par OS si possible
            os_lower = os_name.lower()
            filtered = [t for t in types if os_lower in t]
            if filtered:
                return filtered
        return types

    # Essayer de détecter dynamiquement si netmiko est installé
    try:
        from netmiko import platform_mods
        all_types = platform_mods.get_platform_list()
        matching = [t for t in all_types if vendor_lower in t.lower()]
        if os_name:
            os_filtered = [t for t in matching if os_name.lower() in t.lower()]
            if os_filtered:
                return os_filtered
        return matching
    except (ImportError, AttributeError):
        pass

    return []


# ── ntc-templates ───────────────────────────────────────────────────

def _get_textfsm_commands(vendor: str, os_name: str | None = None) -> list[str]:
    """Retourne les commandes pour lesquelles un template TextFSM existe.

    Scanne l'index ntc-templates si installé.
    """
    commands: list[str] = []

    # Essayer via ntc_templates index
    try:
        from ntc_templates import index as ntc_index

        platform = _vendor_to_ntc_platform(vendor, os_name)
        if platform:
            # L'index est accessible via ntc_index.INDEX
            if hasattr(ntc_index, "INDEX"):
                for entry in ntc_index.INDEX:
                    if entry.get("platform") == platform:
                        cmd = entry.get("command", "")
                        if cmd and cmd not in commands:
                            commands.append(cmd)

    except (ImportError, AttributeError):
        # Fallback: scanner le dossier des templates
        try:
            import ntc_templates
            templates_dir = Path(ntc_templates.__file__).parent / "ntc_templates" / "templates"
            if templates_dir.exists():
                platform = _vendor_to_ntc_platform(vendor, os_name)
                if platform:
                    pattern = f"{platform}_*.textfsm"
                    for f in templates_dir.glob(pattern):
                        # Extraire la commande du nom de fichier
                        # ex: cisco_ios_show_version.textfsm → show version
                        cmd_name = f.stem.replace(f"{platform}_", "", 1)
                        cmd_human = cmd_name.replace("_", " ")
                        if cmd_human not in commands:
                            commands.append(cmd_human)
        except (ImportError, AttributeError):
            pass

    return commands


def _vendor_to_ntc_platform(vendor: str, os_name: str | None = None) -> str | None:
    """Convertit un vendor/os en plateforme ntc-templates.

    Ex: cisco + ios → cisco_ios
        fortinet + fortios → fortinet_fortios
    """
    v = vendor.lower().strip()
    if not os_name:
        return v

    o = os_name.lower().strip()
    return f"{v}_{o}"


# ── Commandes courantes par constructeur ────────────────────────────

_COMMON_COMMANDS: dict[str, list[str]] = {
    "cisco": [
        "show version", "show interfaces", "show ip interface brief",
        "show ip route", "show vlan brief", "show mac address-table",
        "show cdp neighbors detail", "show lldp neighbors detail",
        "show ip bgp summary", "show ip ospf neighbor",
        "show spanning-tree", "show standby brief", "show vrrp brief",
        "show etherchannel summary", "show redundancy",
        "show ip interface", "show access-list",
        "show ip http server status", "show arp",
    ],
    "juniper": [
        "show version", "show interfaces terse", "show interfaces detail",
        "show route", "show lldp neighbors detail",
        "show bgp summary", "show arp",
        "show configuration interfaces",
    ],
    "fortinet": [
        "get system status", "get system interface",
        "get system arp", "show firewall policy",
        "get router info routing-table all",
    ],
    "paloalto": [
        "show system info", "show interface all",
        "show routing route", "show running security-policy",
    ],
    "huawei": [
        "display version", "display interface",
        "display ip routing-table", "display vlan",
        "display mac-address", "display lldp neighbor",
        "display bgp peer", "display arp",
    ],
    "arista": [
        "show version", "show interfaces", "show ip route",
        "show lldp neighbors detail", "show bgp summary",
        "show vlan", "show mac address-table",
        "show spanning-tree", "show arp",
    ],
    "hp": [
        "show version", "show interface brief",
        "show ip route", "show vlan",
        "show lldp info remote-device",
        "show mac-address", "show arp",
    ],
    "dell": [
        "show version", "show interfaces",
        "show ip route", "show vlan",
        "show lldp neighbors", "show mac address-table",
        "show arp",
    ],
    "extreme": [
        "show version", "show ports", "show vlan",
        "show iproute", "show fdb",
        "show lldp neighbors detail",
    ],
}


def _guess_common_commands(vendor: str, os_name: str | None = None) -> list[str]:
    """Devine les commandes typiques pour ce constructeur."""
    vendor_lower = vendor.lower().strip()
    return _COMMON_COMMANDS.get(vendor_lower, [
        "show version", "show interfaces",
        "show ip route", "show arp",
    ])


# ── Profils existants (few-shot) ────────────────────────────────────

def _get_existing_profiles(vendor: str, os_name: str | None = None) -> list[dict[str, Any]]:
    """Récupère les profils existants pour ce vendor comme exemples few-shot.

    Limité à 2 profils maximum pour ne pas surcharger le contexte LLM.
    """
    profiles: list[dict[str, Any]] = []
    if not _PROFILES_DIR.exists():
        return profiles

    vendor_lower = vendor.lower().strip()
    for f in sorted(_PROFILES_DIR.glob("*.yml")):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh)
            if not data:
                continue
            profile_vendor = (data.get("vendor") or "").lower().strip()
            profile_os = (data.get("os") or "").lower().strip()

            # Filtrer par vendor, et optionnellement par OS
            if profile_vendor == vendor_lower:
                if os_name and profile_os == os_name.lower().strip():
                    profiles.append(data)
                    break  # correspondance exacte
                elif not os_name:
                    profiles.append(data)
                    if len(profiles) >= 2:
                        break
        except Exception:
            continue

    return profiles


# ── Exemple de profil (few-shot universel) ─────────────────────────

_EXAMPLE_PROFILE_YAML = """\
name: cisco-ios
vendor: cisco
os: ios
device_role: switch
match_banner:
  - "Cisco"
  - "IOS"
match_cmd_output:
  - "cisco"
  - "ios"
  - "Cisco IOS Software"
transports:
  - type: ssh
    priority: 10
    device_type: cisco_ios
commands:
  show_version: "show version"
  show_interfaces: "show interfaces"
  show_ip_route: "show ip route"
  show_vlan: "show vlan brief"
  show_mac: "show mac address-table"
  show_cdp: "show cdp neighbors detail"
  show_lldp: "show lldp neighbors detail"
  show_bgp: "show ip bgp summary"
  show_access_list: "show access-list"
  show_http_status: "show ip http server status"
  show_arp: "show arp"
command_groups:
  system:
    refs: ["show_version"]
  interfaces:
    refs: ["show_interfaces"]
  routing:
    refs: ["show_ip_route", "show_bgp"]
  switching:
    refs: ["show_vlan", "show_mac"]
  topology:
    refs: ["show_cdp", "show_lldp"]
  security:
    refs: ["show_access_list"]
  services:
    refs: ["show_http_status"]
  endpoints:
    refs: ["show_arp"]
  all:
    refs: ["show_version", "show_interfaces", "show_ip_route",
           "show_vlan", "show_mac", "show_cdp", "show_lldp",
           "show_bgp", "show_access_list", "show_http_status", "show_arp"]
neo4j_labels:
  device: "Device"
  interface: "Interface"
  route: "Route"
  vlan: "VLAN"
fallback:
  transport: ssh
  device_type: cisco_ios
  commands:
    - "show version"
    - "show interfaces"
"""


def get_example_profile() -> str:
    """Retourne un exemple de profil YAML (few-shot pour le LLM)."""
    return _EXAMPLE_PROFILE_YAML
