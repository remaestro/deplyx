#!/usr/bin/env python3
"""
Spawn a realistic enterprise-style lab topology through the Lab API.

What this script does:
- Authenticates to deplyx backend API
- Optionally removes existing lab containers
- Spawns a curated enterprise topology across Network/Security/Application

Usage:
  cd lab
  python3 spawn_enterprise_topology.py
  python3 spawn_enterprise_topology.py --reset

Environment overrides:
  DEPLYX_API_BASE=http://localhost:8000/api/v1
  DEPLYX_ADMIN_EMAIL=labadmin@deplyx.io
  DEPLYX_ADMIN_PASSWORD=LabAdmin123!
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

AUTH_API_BASE = os.getenv("DEPLYX_AUTH_API_BASE", "http://localhost:8000/api/v1")
LAB_API_BASE = os.getenv("DEPLYX_LAB_API_BASE", "http://localhost:8001/api/v1")
ADMIN_EMAIL = os.getenv("DEPLYX_ADMIN_EMAIL", "labadmin@deplyx.io")
ADMIN_PASSWORD = os.getenv("DEPLYX_ADMIN_PASSWORD", "LabAdmin123!")


@dataclass(frozen=True)
class NodeSpec:
    type_id: str
    name: str
    category: str
    role: str
    zone: str
    site: str = "HQ"


ENTERPRISE_TOPOLOGY: list[NodeSpec] = [
    NodeSpec("fortinet", "fw-edge-01", "Firewall", "north-south firewall", "EDGE"),
    NodeSpec("paloalto", "fw-dmz-01", "Firewall", "dmz firewall", "DMZ"),
    NodeSpec("checkpoint", "sec-gw-01", "Firewall", "policy gateway", "SEC"),
    NodeSpec("cisco-router", "rt-wan-01", "Router", "wan edge router", "EDGE"),
    NodeSpec("vyos", "rt-core-01", "Router", "core router", "CORE"),
    NodeSpec("cisco-ios", "sw-core-01", "Switch", "core switch", "CORE"),
    NodeSpec("cisco-nxos", "sw-dc-01", "Switch", "datacenter switch", "DC"),
    NodeSpec("juniper", "sw-dist-01", "Switch", "distribution switch", "CORE"),
    NodeSpec("aruba-switch", "sw-access-01", "Switch", "access switch", "CAMPUS"),
    NodeSpec("cisco-wlc", "wlc-01", "Wireless", "wireless controller", "WLAN"),
    NodeSpec("aruba-ap", "ap-campus-01", "Wireless", "campus access point", "WLAN"),
    NodeSpec("strongswan-vpn", "vpn-remote-01", "Security", "remote access vpn", "SEC"),
    NodeSpec("snort-ids", "ids-dmz-01", "Security", "intrusion detection", "DMZ"),
    NodeSpec("openldap", "ldap-idm-01", "Security", "identity directory", "IDM"),
    NodeSpec("nginx", "web-gw-01", "Application", "reverse proxy", "DMZ"),
    NodeSpec("postgres", "db-main-01", "Application", "primary database", "DATA"),
    NodeSpec("redis", "cache-main-01", "Application", "cache tier", "DATA"),
    NodeSpec("elasticsearch", "search-obs-01", "Application", "search and logs", "OBS"),
    NodeSpec("grafana", "grafana-obs-01", "Application", "dashboards", "OBS"),
    NodeSpec("prometheus", "prom-core-01", "Application", "metrics", "OBS"),
]


def _http_json(base_url: str, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict | list | str]:
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8")
        err.close()
        try:
            return err.code, json.loads(text)
        except json.JSONDecodeError:
            return err.code, text


def get_auth_headers() -> dict[str, str]:
    _http_json(
        AUTH_API_BASE,
        "POST",
        "/auth/register",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "role": "admin"},
    )
    code, payload = _http_json(
        AUTH_API_BASE,
        "POST",
        "/auth/login",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if code != 200 or not isinstance(payload, dict) or "access_token" not in payload:
        raise RuntimeError(f"Authentication failed: {code} {payload}")

    return {"Authorization": f"Bearer {payload['access_token']}"}


def list_lab_containers(headers: dict[str, str]) -> list[dict]:
    code, payload = _http_json(LAB_API_BASE, "GET", "/lab/containers", headers=headers)
    if code != 200 or not isinstance(payload, list):
        raise RuntimeError(f"Failed to list lab containers: {code} {payload}")
    return payload


def remove_all_lab_containers(headers: dict[str, str]) -> None:
    current = list_lab_containers(headers)
    if not current:
        print("No existing lab containers to remove.")
        return

    print(f"Removing {len(current)} existing lab container(s)...")
    for item in current:
        container_id = item.get("id")
        if not container_id:
            continue
        code, payload = _http_json(LAB_API_BASE, "DELETE", f"/lab/containers/{container_id}", headers=headers)
        if code not in (200, 202, 204):
            print(f"  [warn] remove {container_id} failed: {code} {payload}")


def spawn_enterprise_topology(headers: dict[str, str]) -> None:
    existing = list_lab_containers(headers)
    existing_user_names = {c.get("labels", {}).get("deplyx.user_name", "") for c in existing}

    created = 0
    skipped = 0
    failed = 0

    print(f"Deploying enterprise topology ({len(ENTERPRISE_TOPOLOGY)} nodes)...")

    for node in ENTERPRISE_TOPOLOGY:
        if node.name in existing_user_names:
            print(f"  [skip] {node.name} ({node.type_id}) already exists")
            skipped += 1
            continue

        payload = {
            "type_id": node.type_id,
            "name": node.name,
            "custom_env": {
                "ORG_SITE": node.site,
                "ORG_ZONE": node.zone,
                "ORG_ROLE": node.role,
                "ORG_CATEGORY": node.category,
            },
        }
        code, res = _http_json(LAB_API_BASE, "POST", "/lab/containers", payload, headers=headers)
        if code in (200, 201):
            print(f"  [ok] {node.name} ({node.type_id})")
            created += 1
        else:
            print(f"  [fail] {node.name} ({node.type_id}) -> {code} {res}")
            failed += 1

    print("\nSummary")
    print(f"  created: {created}")
    print(f"  skipped: {skipped}")
    print(f"  failed : {failed}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Spawn enterprise lab topology")
    parser.add_argument("--reset", action="store_true", help="remove existing lab containers before spawning")
    args = parser.parse_args()

    try:
        headers = get_auth_headers()
        if args.reset:
            remove_all_lab_containers(headers)
        spawn_enterprise_topology(headers)
        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
