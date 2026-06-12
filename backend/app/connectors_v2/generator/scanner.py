"""Scanner passif d'équipements réseau.

Utilise des méthodes non-intrusives pour identifier le constructeur et l'OS :
  1. Bannière SSH (socket brut, PAS de login)
  2. SNMP sysDescr (lecture seule, communauté public)
  3. Services probing (HTTP, HTTPS)
  4. Sniff ARP (si on est sur le même segment)
"""

from __future__ import annotations

import re
import socket
from typing import Any

from app.connectors_v2.device_profile import DeviceProfile, fingerprint_device
from app.connectors_v2.fingerprint import fingerprint_from_banner
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ── Constantes ──────────────────────────────────────────────────────

SSH_PORT = 22
SNMP_PORT = 161
HTTP_PORTS = [80, 443, 8080, 8443]
BANNER_TIMEOUT = 5
SNMP_TIMEOUT = 3

# Mapping SNMP sysObjectID → vendor (prefixes OID courants)
SNMP_VENDOR_MAP: dict[str, str] = {
    ".1.3.6.1.4.1.9": "cisco",
    ".1.3.6.1.4.1.2636": "juniper",
    ".1.3.6.1.4.1.12356": "fortinet",
    ".1.3.6.1.4.1.25461": "paloalto",
    ".1.3.6.1.4.1.2620": "checkpoint",
    ".1.3.6.1.4.1.6527": "adtran",
    ".1.3.6.1.4.1.1916": "extreme",
    ".1.3.6.1.4.1.1588": "arista",
    ".1.3.6.1.4.1.11": "hp",
    ".1.3.6.1.4.1.674": "dell",
    ".1.3.6.1.4.1.2011": "huawei",
    ".1.3.6.1.4.1.890": "zyxel",
    ".1.3.6.1.4.1.6486": "alcatel",
    ".1.3.6.1.4.1.14823": "aruba",
}


# ── Scanner principal ───────────────────────────────────────────────

async def scan_device(
    host: str,
    *,
    username: str | None = None,
    password: str | None = None,
    enable_password: str | None = None,
    snmp_community: str = "public",
    http_probe: bool = True,
) -> dict[str, Any]:
    """Identifie un équipement en priorité via les **credentials fournis**.

    Le client fournit une liste d'équipements avec leurs credentials —
    c'est le cas réel. On les utilise pour :

    1. Se connecter en SSH avec les vrais identifiants
    2. Exécuter ``show version`` (ou équivalent) pour identifier vendor/OS
    3. Collecter les commandes qui fonctionnent sur cet équipement

    En l'absence de credentials, on tombe en mode passif (bannière, SNMP, HTTP).

    Paramètres
    ----------
    host :
        Adresse IP ou hostname.
    username, password, enable_password :
        Credentials SSH.
    snmp_community :
        Communauté SNMP (défaut: ``public``).
    http_probe :
        Tenter une sonde HTTP/HTTPS.

    Retourne
    --------
    dict avec : vendor, os, os_version, hostname, model, transport,
    source, commands_valides (liste des commandes qui marchent).
    """
    result: dict[str, Any] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
        "transport": None,
        "source": "unknown",
        "commands_valides": [],
        "commands_echouees": [],
    }

    # ── Phase 1 : SSH avec credentials (cas réel) ───────────────
    if username and password:
        logger.info("Scan SSH authentifié pour %s", host)
        auth_info = _scan_ssh_auth(
            host, username, password, enable_password=enable_password
        )
        if auth_info.get("vendor"):
            result.update(auth_info)
            result["transport"] = "ssh"
            result["source"] = "ssh_auth"
            logger.info(
                "SSH auth: %s → %s / %s (hostname=%s)",
                host, result["vendor"], result["os"], result.get("hostname", "?"),
            )

            # Essayer d'autres commandes pour valider le profil
            cmds_valides, cmds_echouees = _probe_commands(
                host, username, password, enable_password,
                result.get("vendor", ""), result.get("os", ""),
            )
            result["commands_valides"] = cmds_valides
            result["commands_echouees"] = cmds_echouees
            logger.info(
                "%s: %d commandes OK, %d échouées",
                host, len(cmds_valides), len(cmds_echouees),
            )
            return result

    # ── Phase 2 : Méthodes passives (secours, sans credentials) ─
    logger.info("Scan passif pour %s (aucun credentials ou échec SSH)", host)

    # 2a. Bannière SSH (socket brut)
    banner_info = _scan_ssh_banner(host)
    if banner_info.get("vendor"):
        result.update(banner_info)
        result["transport"] = "ssh"
        result["source"] = "banner"

    # 2b. SNMP (lecture seule)
    if not result.get("vendor"):
        snmp_info = _scan_snmp(host, snmp_community)
        if snmp_info.get("vendor"):
            result.update(snmp_info)
            result["transport"] = "snmp"
            result["source"] = "snmp"

    # 2c. HTTP / HTTPS probe
    if http_probe and not result.get("vendor"):
        http_info = _scan_http(host)
        if http_info.get("vendor"):
            result.update(http_info)
            result["source"] = "http"

    if not result.get("vendor"):
        logger.info("Aucune identification pour %s", host)

    return result


# ── SSH authentifié (fallback intrusif) ─────────────────────────────

def _scan_ssh_auth(
    host: str,
    username: str,
    password: str,
    enable_password: str | None = None,
) -> dict[str, str | None]:
    """Connexion SSH pour identifier l'équipement et récupérer les infos système.

    C'est la méthode principale — le client fournit les credentials,
    on les utilise pour :
      - ``show version`` (ou équivalent) → vendor, OS, hostname, version
      - ``show running-config | include hostname`` → hostname
    """
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }

    try:
        from app.connectors_v2.fingerprint import fingerprint_from_cmd_output
        from app.connectors_v2.transports import SSHTransport

        ssh = SSHTransport(
            host=host,
            port=22,
            username=username,
            password=password,
            enable_password=enable_password or password,
            conn_timeout=10,
            cmd_timeout=15,
        )

        if not ssh.connect():
            return result

        # show version → fingerprint + infos système
        try:
            out = ssh.run_command("show version")
        except Exception:
            out = ""

        if out:
            profiles = DeviceProfile.load_all()
            fp = fingerprint_from_cmd_output(out, profiles)
            result.update(fp)

            m = re.search(r"(\S+)\s+uptime", out, re.IGNORECASE)
            if m:
                result["hostname"] = m.group(1)
            m = re.search(r"Version\s+([\d.]+)", out, re.IGNORECASE)
            if m:
                result["os_version"] = m.group(1)
            m = re.search(r"Processor board ID\s+(\S+)", out, re.IGNORECASE)
            if m:
                result["model"] = m.group(1)

        # Si show version n'a pas donné d'hostname, essayer hostname
        if not result.get("hostname"):
            try:
                out = ssh.run_command("hostname")
                if out and len(out.strip()) < 100:
                    result["hostname"] = out.strip()
            except Exception:
                pass

        ssh.disconnect()

    except Exception as exc:
        logger.debug("SSH auth scan error for %s: %s", host, exc)

    return result


def _probe_commands(
    host: str,
    username: str,
    password: str,
    enable_password: str | None = None,
    vendor: str = "",
    os_name: str = "",
) -> tuple[list[str], list[str]]:
    """Teste une série de commandes courantes sur l'équipement.

    Retourne (commandes_valides, commandes_echouees).
    Utile pour savoir quelles commandes mettre dans le profil YAML.
    """
    valides: list[str] = []
    echouees: list[str] = []

    # Commandes à tester selon le vendor/OS
    vendor_lower = vendor.lower().strip()
    os_lower = os_name.lower().strip() if os_name else ""

    if os_lower in ("ios", "iosxe") or vendor_lower == "cisco":
        candidates = [
            "show version",
            "show interfaces",
            "show ip interface brief",
            "show ip route",
            "show vlan brief",
            "show mac address-table",
            "show cdp neighbors detail",
            "show lldp neighbors detail",
            "show ip bgp summary",
            "show standby brief",
            "show access-list",
            "show arp",
        ]
    elif os_lower in ("fortios",) or vendor_lower == "fortinet":
        candidates = [
            "get system status",
            "get system interface",
            "get system arp",
            "show firewall policy",
            "get router info routing-table all",
        ]
    elif os_lower in ("junos",) or vendor_lower == "juniper":
        candidates = [
            "show version",
            "show interfaces terse",
            "show route",
            "show lldp neighbors",
            "show arp",
        ]
    else:
        candidates = [
            "show version",
            "show interfaces",
            "show ip route",
            "show arp",
        ]

    try:
        from app.connectors_v2.transports import SSHTransport

        ssh = SSHTransport(
            host=host,
            port=22,
            username=username,
            password=password,
            enable_password=enable_password or password,
            conn_timeout=10,
            cmd_timeout=10,
        )

        if not ssh.connect():
            return valides, echouees

        for cmd in candidates:
            try:
                out = ssh.run_command(cmd)
                if out and len(out.strip()) > 20:
                    valides.append(cmd)
                else:
                    echouees.append(cmd)
            except Exception:
                echouees.append(cmd)

        ssh.disconnect()

    except Exception as exc:
        logger.debug("Command probe error for %s: %s", host, exc)

    return valides, echouees


# ── SSH Banner (passif) ─────────────────────────────────────────────

def _scan_ssh_banner(host: str) -> dict[str, str | None]:
    """Récupère la bannière SSH sans authentification."""
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(BANNER_TIMEOUT)
        sock.connect((host, SSH_PORT))
        banner = sock.recv(4096).decode(errors="ignore").strip()
        sock.close()

        if not banner:
            return result

        # Utiliser le fingerprint profile-driven + legacy fallback
        profiles = DeviceProfile.load_all()
        fp = fingerprint_from_banner(banner, profiles)
        result.update(fp)

        # Extraire hostname de la bannière si possible
        # Format SSH-2.0-xxx ou bannière constructeur
        hostname_match = re.search(
            r"(?:Hostname|hostname)\s*[=:]\s*(\S+)", banner, re.IGNORECASE
        )
        if hostname_match:
            result["hostname"] = hostname_match.group(1)

    except (socket.timeout, ConnectionRefusedError, OSError):
        pass
    except Exception as exc:
        logger.debug("SSH banner scan error for %s: %s", host, exc)

    return result


# ── SNMP ────────────────────────────────────────────────────────────

def _scan_snmp(host: str, community: str = "public") -> dict[str, str | None]:
    """Interroge sysDescr et sysObjectID via SNMP v2c.

    Retourne un dict partiellement renseigné (vendor, hostname, model).
    """
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }

    try:
        from pysnmp.hlapi import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            getCmd,
        )
    except ImportError:
        logger.debug("pysnmp not available, skipping SNMP scan")
        return result

    oids = [
        ".1.3.6.1.2.1.1.1.0",   # sysDescr
        ".1.3.6.1.2.1.1.5.0",   # sysName
        ".1.3.6.1.2.1.1.2.0",   # sysObjectID
    ]

    try:
        error_indication, error_status, error_index, var_binds = next(
            getCmd(
                SnmpEngine(),
                CommunityData(community),
                UdpTransportTarget((host, 161), timeout=SNMP_TIMEOUT, retries=1),
                ContextData(),
                *[ObjectType(ObjectIdentity(oid)) for oid in oids],
            )
        )

        if error_indication or error_status:
            return result

        sys_descr = ""
        sys_name = ""
        sys_object_id = ""

        for var_bind in var_binds:
            oid = str(var_bind[0])
            val = str(var_bind[1])
            if ".1.3.6.1.2.1.1.1.0" in oid:
                sys_descr = val
            elif ".1.3.6.1.2.1.1.5.0" in oid:
                sys_name = val
            elif ".1.3.6.1.2.1.1.2.0" in oid:
                sys_object_id = val

        if sys_name:
            result["hostname"] = sys_name

        # Identifier le vendor via sysObjectID
        if sys_object_id:
            for oid_prefix, vendor in SNMP_VENDOR_MAP.items():
                if sys_object_id.startswith(oid_prefix):
                    result["vendor"] = vendor
                    break

        # Extraire OS depuis sysDescr
        if sys_descr:
            descr_lower = sys_descr.lower()
            for keyword, os_name in [
                ("ios", "ios"),
                ("nx-os", "nxos"),
                ("ftd", "ftd"),
                ("asa", "asa"),
                ("junos", "junos"),
                ("fortinet", "fortios"),
                ("fortigate", "fortios"),
                ("panos", "panos"),
                ("palo alto", "panos"),
                ("vyos", "vyos"),
                ("vyatta", "vyos"),
                ("linux", "linux"),
                ("aruba", "aruba"),
            ]:
                if keyword in descr_lower:
                    result["os"] = os_name
                    break

            # Extraire version
            ver_match = re.search(r"Version\s+([\d.]+)", sys_descr, re.IGNORECASE)
            if ver_match:
                result["os_version"] = ver_match.group(1)

    except Exception as exc:
        logger.debug("SNMP scan error for %s: %s", host, exc)

    return result


# ── HTTP probe ──────────────────────────────────────────────────────

def _scan_http(host: str) -> dict[str, str | None]:
    """Tente une sonde HTTP/HTTPS pour identifier le constructeur.

    Certains équipements (Palo Alto, Fortinet) exposent une page de login
    avec des indices sur le constructeur.
    """
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    try:
        import requests

        for port in HTTP_PORTS:
            scheme = "https" if port in (443, 8443) else "http"
            try:
                resp = requests.get(
                    f"{scheme}://{host}:{port}",
                    timeout=3,
                    verify=False,
                    headers={"User-Agent": "DeplyxScanner/1.0"},
                )
                body = resp.text.lower()

                # Patterns de constructeurs dans les pages web
                vendor_checks = [
                    ("fortinet", ["fortinet", "fortigate"]),
                    ("paloalto", ["pan-os", "paloaltonetworks"]),
                    ("cisco", ["cisco systems", "cisco asa"]),
                    ("checkpoint", ["check point", "checkpoint"]),
                    ("huawei", ["huawei technologies"]),
                    ("aruba", ["aruba networks"]),
                    ("hp", ["hewlett packard", "procurve"]),
                ]
                for vendor, keywords in vendor_checks:
                    if any(kw in body for kw in keywords):
                        result["vendor"] = vendor
                        return result

            except (requests.RequestException, ConnectionError):
                continue

    except ImportError:
        pass
    except Exception as exc:
        logger.debug("HTTP scan error for %s: %s", host, exc)

    return result
