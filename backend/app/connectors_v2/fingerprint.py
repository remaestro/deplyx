"""
Reconnaissance d'équipements réseau (fingerprinting) pilotée par les profils YAML.

Le principe :
  1. Itérer sur tous les profils chargés.
  2. Pour chaque profil, tester ses patterns ``match_banner`` / ``match_cmd_output``
     contre le texte brut (bannière SSH ou sortie de commande).
  3. Dès qu'un profil matche, retourner ses métadonnées (vendor, os, …).
  4. Si aucun profil ne matche, utiliser la logique hardcodée comme fallback
     (pour les constructeurs qui n'ont pas encore de profil YAML).

Ce module remplace progressivement les fonctions ``_fingerprint_from_banner()``
et ``_fingerprint_from_ssh_cmd()`` de ``device_profile.py``.
"""

from __future__ import annotations

import re
from typing import Any

from app.connectors_v2.device_profile import DeviceProfile


def fingerprint_from_banner(
    banner: str,
    profiles: dict[str, DeviceProfile] | None = None,
) -> dict[str, str | None]:
    """Identifie un équipement depuis sa bannière SSH.

    Essaie d'abord les profils YAML (``match_banner``),
    puis tombe dans la logique hardcodée historique.
    """
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }

    # 1. Profile-driven matching
    if profiles is not None:
        match = _match_banner_against_profiles(banner, profiles)
        if match:
            result.update(match)
            return result

    # 2. Fallback hardcodé
    return _legacy_fingerprint_from_banner(banner)


def fingerprint_from_cmd_output(
    output: str,
    profiles: dict[str, DeviceProfile] | None = None,
) -> dict[str, str | None]:
    """Identifie un équipement depuis la sortie d'une commande (show version…).

    Essaie d'abord les profils YAML (``match_cmd_output``),
    puis tombe dans la logique hardcodée historique.
    """
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }

    # 1. Profile-driven matching
    if profiles is not None:
        match = _match_cmd_output_against_profiles(output, profiles)
        if match:
            result.update(match)
            return result

    # 2. Fallback hardcodé
    return _legacy_fingerprint_from_cmd_output(output)


# ── Profile-driven matching ────────────────────────────────────────

def _match_banner_against_profiles(
    banner: str,
    profiles: dict[str, DeviceProfile],
) -> dict[str, str | None] | None:
    """Itère sur les profils et retourne le premier dont ``match_banner`` matche."""
    banner_lower = banner.lower()
    for profile in profiles.values():
        if not profile.match_banner:
            continue
        for pattern in profile.match_banner:
            if pattern.lower() in banner_lower:
                return {
                    "vendor": profile.vendor or None,
                    "os": profile.os or None,
                    "os_version": None,
                    "hostname": None,
                    "model": None,
                }
    return None


def _match_cmd_output_against_profiles(
    output: str,
    profiles: dict[str, DeviceProfile],
) -> dict[str, str | None] | None:
    """Itère sur les profils et retourne le premier dont ``match_cmd_output`` matche."""
    output_lower = output.lower()
    for profile in profiles.values():
        if not profile.match_cmd_output:
            continue
        for pattern in profile.match_cmd_output:
            if pattern.lower() in output_lower:
                return {
                    "vendor": profile.vendor or None,
                    "os": profile.os or None,
                    "os_version": None,
                    "hostname": None,
                    "model": None,
                }
    return None


# ── Legacy fallback (hardcodé) ─────────────────────────────────────

def _clean_version(raw: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]", "", raw.strip())


def _legacy_fingerprint_from_banner(banner: str) -> dict[str, str | None]:
    """Logique hardcodée historique — sera supprimée quand tous les profils
    auront leurs patterns ``match_banner`` renseignés."""
    banner_lower = banner.lower()
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }

    if "ssh-" in banner_lower:
        result["vendor"] = "generic"

    if "cisco" in banner_lower:
        result["vendor"] = "cisco"
        if "ftd" in banner_lower:
            result["os"] = "ftd"
        elif "ios" in banner_lower and "nx-os" not in banner_lower:
            result["os"] = "ios"
        elif "nx-os" in banner_lower:
            result["os"] = "nxos"
        elif "asa" in banner_lower:
            result["os"] = "asa"
    elif "juniper" in banner_lower:
        result["vendor"] = "juniper"
        result["os"] = "junos"
    elif "palo alto" in banner_lower or "panos" in banner_lower:
        result["vendor"] = "paloalto"
        result["os"] = "panos"
    elif "fortinet" in banner_lower or "fortigate" in banner_lower:
        result["vendor"] = "fortinet"
        result["os"] = "fortios"
    elif "vyatta" in banner_lower or "vyos" in banner_lower:
        result["vendor"] = "vyos"
        result["os"] = "vyos"
    elif "aruba" in banner_lower:
        result["vendor"] = "aruba"
        result["os"] = "aruba"
    elif "checkpoint" in banner_lower or "check point" in banner_lower:
        result["vendor"] = "checkpoint"
        result["os"] = "checkpoint"
    elif "linux" in banner_lower:
        result["vendor"] = "linux"

    return result


def _legacy_fingerprint_from_cmd_output(
    output: str,
) -> dict[str, str | None]:
    """Logique hardcodée historique — sera supprimée quand tous les profils
    auront leurs patterns ``match_cmd_output`` renseignés."""
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }

    lower = output.lower()

    if "cisco" in lower or "ios" in lower:
        result["vendor"] = "cisco"
        if "nx-os" in lower or "nxos" in lower:
            result["os"] = "nxos"
        elif "ftd" in lower or "firepower" in lower:
            result["os"] = "ftd"
        elif "asa" in lower:
            result["os"] = "asa"
        else:
            result["os"] = "ios"
        m = re.search(r"Version\s+([\d.]+)", output, re.IGNORECASE)
        if m:
            result["os_version"] = _clean_version(m.group(1))
        m = re.search(r"Processor board ID\s+(\S+)", output, re.IGNORECASE)
        if m:
            result["model"] = m.group(1)
        m = re.search(r"(\S+)\s+uptime", output, re.IGNORECASE)
        if m:
            result["hostname"] = m.group(1)
        return result

    if "junos" in lower:
        result["vendor"] = "juniper"
        result["os"] = "junos"
        m = re.search(r"Junos:\s*([\d.]+)", output, re.IGNORECASE)
        if m:
            result["os_version"] = _clean_version(m.group(1))
        return result

    if "vyos" in lower or "vyatta" in lower:
        result["vendor"] = "vyos"
        result["os"] = "vyos"
        m = re.search(r"Version:\s*(\S+)", output, re.IGNORECASE)
        if m:
            result["os_version"] = _clean_version(m.group(1))
        return result

    if "fortinet" in lower or "fortigate" in lower:
        result["vendor"] = "fortinet"
        result["os"] = "fortios"
        return result

    if "palo" in lower or "panos" in lower:
        result["vendor"] = "paloalto"
        result["os"] = "panos"
        return result

    if "linux" in lower:
        result["vendor"] = "linux"
        m = re.search(r'PRETTY_NAME=["\']?(.+?)["\']?$', output, re.MULTILINE)
        if m:
            result["os"] = "linux"
            result["os_version"] = _clean_version(m.group(1))
        return result

    if "aruba" in lower:
        result["vendor"] = "aruba"
        result["os"] = "aruba"
        return result

    return result


# ── Enrichissement des profils manquants ──────────────────────────

def enrich_profile_match_patterns(
    profile: DeviceProfile,
    profiles: dict[str, DeviceProfile],
) -> DeviceProfile:
    """Ajoute automatiquement les patterns de ``match_banner`` / ``match_cmd_output``
    à un profil qui en est dépourvu, en se basant sur son vendor/os.

    Utile pour les profils legacy comme ``cisco-router.yml`` ou ``generic-ssh.yml``
    qui ont des listes vides.
    """
    vendor_lower = (profile.vendor or "").lower()
    os_lower = (profile.os or "").lower()

    # Si déjà renseigné, ne rien faire
    if profile.match_banner or profile.match_cmd_output:
        return profile

    # Suggestions par vendor
    banner_hints: list[str] = []
    cmd_hints: list[str] = []

    if vendor_lower == "cisco":
        if os_lower == "ios":
            banner_hints = ["Cisco", "IOS"]
            cmd_hints = ["cisco", "ios", "Cisco IOS Software"]
        elif os_lower == "nxos":
            banner_hints = ["NX-OS"]
            cmd_hints = ["nx-os", "nxos", "NX-OS"]
        elif os_lower == "ftd":
            banner_hints = ["FTD", "Firepower"]
            cmd_hints = ["ftd", "firepower", "Cisco Firepower"]
        elif os_lower == "asa":
            banner_hints = ["ASA"]
            cmd_hints = ["asa", "Cisco ASA"]
        else:
            banner_hints = ["Cisco"]
            cmd_hints = ["cisco"]
    elif vendor_lower == "fortinet":
        banner_hints = ["Fortinet", "FortiGate"]
        cmd_hints = ["fortinet", "fortigate", "FortiGate"]
    elif vendor_lower == "paloalto":
        banner_hints = ["Palo Alto", "PAN-OS"]
        cmd_hints = ["palo", "panos", "PAN-OS"]
    elif vendor_lower == "juniper":
        banner_hints = ["Juniper", "Junos"]
        cmd_hints = ["junos", "Juniper"]
    elif vendor_lower == "linux":
        banner_hints = ["Linux"]
        cmd_hints = ["linux"]
    elif vendor_lower == "vyos":
        banner_hints = ["VyOS", "Vyatta"]
        cmd_hints = ["vyos", "vyatta", "VyOS"]
    elif vendor_lower == "aruba":
        banner_hints = ["Aruba"]
        cmd_hints = ["aruba"]
    elif vendor_lower == "checkpoint":
        banner_hints = ["Check Point"]
        cmd_hints = ["checkpoint", "Check Point"]

    if banner_hints or cmd_hints:
        # On ne mute pas l'original ; on retourne un nouvel objet config
        new_data = {
            "name": profile.name,
            "vendor": profile.vendor,
            "os": profile.os,
            "match_banner": banner_hints,
            "match_cmd_output": cmd_hints,
            "transports": profile.transports,
            "commands": profile.commands,
            "command_groups": profile.command_groups,
            "parsers": profile.parsers,
            "neo4j_labels": profile.neo4j_labels,
            "device_role": profile.device_role,
            "api_discovery": profile.api_discovery,
            "fallback": profile.fallback,
        }
        return DeviceProfile(new_data)

    return profile
