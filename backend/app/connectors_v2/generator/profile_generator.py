"""Générateur de profils YAML par LLM.

Orchestre le scan, la collecte de doc et la synthèse LLM pour produire
un profil YAML prêt à l'emploi.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from app.connectors_v2.generator.doc_collector import (
    collect_device_info,
    get_example_profile,
)
from app.connectors_v2.generator.scanner import scan_device
from app.utils.logging import get_logger

logger = get_logger(__name__)

_PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"

# ── Prompt LLM ──────────────────────────────────────────────────────

_PROFILE_GENERATION_PROMPT = """Tu es un expert en automatisation réseau. Tu dois générer un profil YAML Deplyx pour un équipement réseau.

## Contexte

- Constructeur : {vendor}
- OS : {os_name}
- Device types Netmiko disponibles : {device_types}
- Commandes avec template TextFSM : {commands_with_templates}
- Commandes probables (sans template confirmé) : {commands_without_templates}
- Commandes VALIDÉES sur l'équipement réel : {validated_commands}

## Profils existants comme exemple (few-shot)

```yaml
{example_profile}
```

## Format attendu

Le profil YAML doit respecter cette structure :

```yaml
name: <vendor>-<os>
vendor: <vendor>
os: <os>
device_role: <firewall|switch|router|wlc|access-point|vpn-gateway|ids|server>
match_banner:
  - "<motif dans bannière SSH>"
match_cmd_output:
  - "<motif dans sortie show version>"
transports:
  - type: ssh
    priority: 10
    device_type: <netmiko_device_type>
commands:
  show_version: "<commande>"
  show_interfaces: "<commande>"
  show_ip_route: "<commande>"
  show_vlan: "<commande>"
  show_mac: "<commande>"
  show_cdp: "<commande>"
  show_lldp: "<commande>"
  show_bgp: "<commande>"
  show_arp: "<commande>"
command_groups:
  system:
    refs: ["show_version"]
  interfaces:
    refs: ["show_interfaces"]
  routing:
    refs: ["show_ip_route"]
  switching:
    refs: ["show_vlan", "show_mac"]
  topology:
    refs: ["show_cdp", "show_lldp"]
  endpoints:
    refs: ["show_arp"]
  all:
    refs: ["show_version", "show_interfaces", "show_ip_route",
           "show_vlan", "show_mac", "show_cdp", "show_lldp",
           "show_bgp", "show_arp"]
neo4j_labels:
  device: "Device"
  interface: "Interface"
  route: "Route"
  vlan: "VLAN"
fallback:
  transport: ssh
  device_type: <netmiko_device_type>
  commands:
    - "show version"
    - "show interfaces"
```

## Règles

1. Les commandes doivent être adaptées au constructeur (ex: Huawei utilise "display" pas "show").
2. `match_banner` et `match_cmd_output` doivent contenir des mots-clés qui permettent d'identifier ce constructeur/OS.
3. Le `device_type` du transport SSH doit être un type Netmiko valide.
4. Les commandes dans `commands` doivent utiliser des noms courts en snake_case.
5. `command_groups` doit organiser les commandes par catégorie fonctionnelle.
6. Si l'OS est un firewall (FTD, FortiOS, PAN-OS), utiliser ``device_role: firewall``.
7. Si l'OS est un OS de switch (IOS, NX-OS), utiliser ``device_role: switch``.
8. Si l'OS est un OS de routeur (IOS-XR, VyOS), utiliser ``device_role: router``.

## Output

Génère UNIQUEMENT le YAML, sans commentaire avant ni après.
"""


# ── Générateur principal ───────────────────────────────────────────

async def generate_profile(
    host: str | None = None,
    *,
    vendor: str | None = None,
    os_name: str | None = None,
    username: str | None = None,
    password: str | None = None,
    snmp_community: str = "public",
    output_path: str | Path | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Génère un profil YAML pour un constructeur/OS.

    Deux modes de fonctionnement :

    1. **Mode auto** (host fourni) :
       Scanne l'équipement, collecte la doc, LLM génère le YAML.

    2. **Mode manuel** (vendor + os_name fournis) :
       Collecte la doc uniquement, LLM génère le YAML.

    Paramètres
    ----------
    host :
        IP ou hostname de l'équipement à scanner (optionnel).
    vendor :
        Nom du constructeur (ex: ``cisco``, ``fortinet``).
    os_name :
        Nom de l'OS (ex: ``ios``, ``fortios``).
    username, password :
        Credentials pour le scan SSH optionnel.
    snmp_community :
        Communauté SNMP (défaut: ``public``).
    output_path :
        Chemin où écrire le fichier YAML généré. Par défaut,
        dans ``profiles/`` avec le nom ``<vendor>-<os>.yml``.
    llm_api_key, llm_model, llm_base_url :
        Surcharge de la config LLM (sinon utilise les valeurs de
        l'environnement).

    Retourne
    --------
    dict avec les clés : status, profile (dict YAML), path (chemin fichier),
    yaml_str, errors.
    """
    result: dict[str, Any] = {
        "status": "ok",
        "profile": {},
        "path": None,
        "yaml_str": "",
        "errors": [],
    }

    # ── Phase 1 : Scan (si host fourni) ─────────────────────────
    scan_result = {"vendor": vendor, "os": os_name}
    if host:
        try:
            scan_result = await scan_device(
                host,
                username=username,
                password=password,
                snmp_community=snmp_community,
                http_probe=True,
            )
            logger.info(
                "Scan de %s: vendor=%s os=%s source=%s "
                "(%d commandes OK, %d échouées)",
                host, scan_result.get("vendor"), scan_result.get("os"),
                scan_result.get("source"),
                len(scan_result.get("commands_valides", [])),
                len(scan_result.get("commands_echouees", [])),
            )

            # Si on a des commandes validées, on les passe au LLM
            validated = scan_result.get("commands_valides", [])
            if validated:
                doc.setdefault("commands_validees", validated)
        except Exception as exc:
            result["errors"].append(f"scan: {exc}")
            logger.warning("Scan failed for %s: %s", host, exc)

    # Priorité aux infos du scan, puis aux paramètres
    vendor = scan_result.get("vendor") or vendor
    os_name = scan_result.get("os") or os_name

    if not vendor:
        result["status"] = "error"
        result["errors"].append(
            "Impossible d'identifier le constructeur. "
            "Fournissez vendor= ou un host accessible."
        )
        return result

    # ── Phase 2 : Collecte documentation ────────────────────────
    doc = collect_device_info(vendor, os_name)
    logger.info(
        "Doc collectée pour %s/%s: %d commands, %d templates",
        vendor, os_name or "?",
        len(doc.get("commands_disponibles", [])),
        len(doc.get("commands_avec_template", [])),
    )

    if not doc["device_types_netmiko"]:
        result["errors"].append(
            f"Aucun device_type Netmiko trouvé pour {vendor}/{os_name}"
        )

    # ── Phase 3 : Synthèse LLM ──────────────────────────────────
    llm_response = await _call_llm_for_profile(
        vendor=vendor,
        os_name=os_name or "",
        device_types=doc["device_types_netmiko"],
        commands_with_templates=doc["commands_avec_template"],
        commands_without_templates=doc["commands_sans_template"],
        validated_commands=doc.get("commands_validees"),
        example_profile=get_example_profile(),
        api_key=llm_api_key,
        model=llm_model,
        base_url=llm_base_url,
    )

    if not llm_response:
        logger.warning("LLM n'a pas généré de profil, utilisation du fallback")
        result["errors"].append("LLM n'a pas généré de profil — fallback utilisé")
        fallback_device_type = doc.get("device_types_netmiko", [None])[0] or "unknown"
        llm_response = _generate_fallback_profile(
            vendor, os_name or "", [fallback_device_type]
        )

    # ── Phase 4 : Parsing du YAML généré ────────────────────────
    try:
        profile_data = _parse_llm_yaml(llm_response)
    except (ValueError, yaml.YAMLError) as exc:
        logger.warning("LLM a retourné un YAML invalide, utilisation du fallback. Erreur: %s", exc)
        logger.debug("Réponse LLM brute:\n%s", llm_response)
        result["errors"].append(f"Parsing YAML: {exc} — fallback utilisé")
        # Fallback sur le profil minimal
        fallback_device_type = doc.get("device_types_netmiko", [None])[0] or "unknown"
        llm_response = _generate_fallback_profile(
            vendor, os_name or "", [fallback_device_type]
        )
        profile_data = _parse_llm_yaml(llm_response)

    # Ajouter le nom du profil basé sur vendor+os
    profile_data.setdefault("name", f"{vendor}-{os_name or 'generic'}")

    result["profile"] = profile_data
    result["yaml_str"] = yaml.safe_dump(profile_data, default_flow_style=False, sort_keys=False)

    # ── Phase 5 : Écriture du fichier ───────────────────────────
    if not output_path:
        filename = f"{vendor}-{os_name or 'generic'}.yml"
        output_path = _PROFILES_DIR / filename

    output_path = Path(output_path)
    # Ne pas écraser un profil existant sauf si overwrite=True
    if output_path.exists() and not overwrite:
        result["status"] = "skipped"
        result["errors"].append(
            f"Le fichier {output_path} existe déjà. "
            f"Utilisez overwrite=True pour forcer l'écrasement."
        )
        result["path"] = str(output_path)
        return result

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(output_path, "w") as fh:
            yaml.safe_dump(profile_data, fh, default_flow_style=False, sort_keys=False)
        result["path"] = str(output_path)
        logger.info("Profil généré : %s", output_path)
    except OSError as exc:
        result["errors"].append(f"écriture: {exc}")

    return result


# ── Appel LLM ───────────────────────────────────────────────────────

def _clean_llm_response(content: str) -> str:
    """Nettoie la réponse LLM pour extraire le YAML.

    Gère :
    - Markdown ```yaml ... ``` blocks
    - Markdown ``` ... ``` blocks
    - Texte avant/après le YAML
    - Guillemets non fermés (troncature)
    """
    content = content.strip()

    # Retirer les blocs markdown
    if "```" in content:
        parts = content.split("```")
        for i, part in enumerate(parts):
            part = part.strip()
            if part.lower().startswith("yaml"):
                part = part[4:].strip()
            if part and not part.startswith("```"):
                content = part
                break

    # Si la chaîne commence par `{`, c'est du JSON pas du YAML
    if content.startswith("{"):
        return content

    # Tenter de fermer les guillemets et crochets non fermés
    # (cas de troncature)
    if content.count('"') % 2 != 0:
        content += '"'
    if content.count("'") % 2 != 0:
        content += "'"
    if content.count("[") > content.count("]"):
        content += "]" * (content.count("[") - content.count("]"))
    if content.count("{") > content.count("}"):
        content += "}" * (content.count("{") - content.count("}"))

    return content


async def _call_llm_for_profile(
    vendor: str,
    os_name: str,
    device_types: list[str],
    commands_with_templates: list[str],
    commands_without_templates: list[str],
    validated_commands: list[str] | None = None,
    example_profile: str = "",
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Appelle le LLM configuré pour générer le profil YAML."""
    prompt = _PROFILE_GENERATION_PROMPT.format(
        vendor=vendor,
        os_name=os_name or "generic",
        device_types=json.dumps(device_types),
        commands_with_templates=json.dumps(commands_with_templates),
        commands_without_templates=json.dumps(commands_without_templates),
        validated_commands=json.dumps(validated_commands or []),
        example_profile=example_profile or get_example_profile(),
    )

    # Utiliser la config existante de l'application
    api_key = api_key or os.environ.get("LLM_API_KEY", "")
    model = model or os.environ.get("LLM_MODEL", "deepseek-v4-pro")
    base_url = base_url or os.environ.get("LLM_BASE_URL", "https://opencode.ai/zen/go/v1")

    if not api_key:
        logger.warning("LLM_API_KEY non configurée")
        return _generate_fallback_profile(vendor, os_name, device_types)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Tu génères des profils YAML pour Deplyx."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        content = response.choices[0].message.content
        if content:
            return _clean_llm_response(content)

    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return _generate_fallback_profile(vendor, os_name, device_types)

    return None


def _generate_fallback_profile(
    vendor: str,
    os_name: str,
    device_types: list[str],
) -> str:
    """Génère un profil YAML minimal sans LLM (fallback)."""
    dt = device_types[0] if device_types else f"{vendor}_{os_name}"
    role = _guess_role(vendor, os_name)
    profile = {
        "name": f"{vendor}-{os_name or 'generic'}",
        "vendor": vendor,
        "os": os_name or "generic",
        "device_role": role,
        "transports": [
            {"type": "ssh", "priority": 10, "device_type": dt},
        ],
        "commands": {
            "show_version": "show version",
            "show_interfaces": "show interfaces",
            "show_ip_route": "show ip route",
        },
        "command_groups": {
            "system": {"refs": ["show_version"]},
            "interfaces": {"refs": ["show_interfaces"]},
            "routing": {"refs": ["show_ip_route"]},
            "all": {"refs": ["show_version", "show_interfaces", "show_ip_route"]},
        },
        "neo4j_labels": {
            "device": "Device",
            "interface": "Interface",
        },
        "fallback": {
            "transport": "ssh",
            "device_type": dt,
            "commands": ["show version", "show interfaces"],
        },
    }
    return yaml.safe_dump(profile, default_flow_style=False, sort_keys=False)


def _guess_role(vendor: str, os_name: str) -> str:
    """Devine le rôle de l'équipement."""
    v = vendor.lower().strip()
    o = os_name.lower().strip() if os_name else ""
    if o in ("ftd", "asa", "fortios", "panos") or v in ("fortinet", "paloalto", "checkpoint"):
        return "firewall"
    if o in ("nxos",):
        return "distribution-switch"
    if v == "juniper":
        return "router"
    if v in ("aruba",):
        return "access-point" if "ap" in o else "switch"
    if v == "cisco" and "wlc" in o:
        return "wlc"
    return "switch"


# ── Parsing YAML ────────────────────────────────────────────────────

def _parse_llm_yaml(yaml_str: str) -> dict[str, Any]:
    """Parse la réponse YAML du LLM et valide la structure minimale."""
    data = yaml.safe_load(yaml_str)
    if not isinstance(data, dict):
        raise ValueError("La réponse n'est pas un dictionnaire YAML")

    # Validation minimale
    required = ["vendor", "transports", "commands"]
    missing = [r for r in required if r not in data]
    if missing:
        raise ValueError(f"Champs obligatoires manquants: {missing}")

    if not data.get("transports"):
        raise ValueError("Au moins un transport est requis")

    # S'assurer que les commandes ont des valeurs en string
    commands = data.get("commands", {})
    for cmd_name, cmd_value in commands.items():
        if not isinstance(cmd_value, str):
            raise ValueError(f"La commande '{cmd_name}' doit être une chaîne")

    return data
