#!/usr/bin/env python3
"""Register all lab mock devices as connectors in deplyx via the API.

Run this after the lab mock devices are up and the main stack is running:
    python3 register-devices.py

Environment overrides:
    DEPLYX_API_BASE=http://localhost:8000/api/v1
    DEPLYX_ADMIN_EMAIL=labadmin@deplyx.io
    DEPLYX_ADMIN_PASSWORD=LabAdmin123!
"""

import os
import sys

import requests

API_BASE = os.getenv("DEPLYX_API_BASE", "http://localhost:8000/api/v1")
ADMIN_EMAIL = os.getenv("DEPLYX_ADMIN_EMAIL", "labadmin@deplyx.io")
ADMIN_PASSWORD = os.getenv("DEPLYX_ADMIN_PASSWORD", "LabAdmin123!")


def get_auth_headers() -> dict[str, str]:
    """Register admin user (if needed) and get auth token."""
    # Try to register
    requests.post(
        f"{API_BASE}/auth/register",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "role": "admin"},
    )
    # Login
    res = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if res.status_code != 200:
        print(f"Login failed: {res.text}")
        sys.exit(1)
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


SUPPORTED_TYPE_IDS = {"fortinet", "paloalto", "checkpoint", "cisco-ios", "cisco-nxos", "juniper"}


def to_connector_payload(container: dict) -> dict | None:
    type_id = container.get("type_id", "")
    host = container.get("ip", "")
    name = container.get("name", container.get("id", "lab-device"))
    if type_id not in SUPPORTED_TYPE_IDS or not host:
        return None

    if type_id == "fortinet":
        return {
            "name": f"{name} (Fortinet)",
            "connector_type": "fortinet",
            "config": {
                "host": host,
                "api_token": os.getenv("FORTINET_API_TOKEN", "fg-lab-token-001"),
                "verify_ssl": False,
            },
            "sync_mode": "on-demand",
            "sync_interval_minutes": 30,
        }

    if type_id == "paloalto":
        return {
            "name": f"{name} (Palo Alto)",
            "connector_type": "paloalto",
            "config": {
                "host": host,
                "api_key": os.getenv("PALOALTO_API_KEY", "pa-lab-apikey-001"),
                "verify_ssl": False,
            },
            "sync_mode": "on-demand",
            "sync_interval_minutes": 30,
        }

    if type_id == "checkpoint":
        return {
            "name": f"{name} (Check Point)",
            "connector_type": "checkpoint",
            "config": {
                "host": host,
                "username": os.getenv("CHECKPOINT_USER", "admin"),
                "password": os.getenv("CHECKPOINT_PASS", "Cp@ssw0rd!"),
                "verify_ssl": False,
            },
            "sync_mode": "on-demand",
            "sync_interval_minutes": 60,
        }

    if type_id in {"cisco-ios", "cisco-nxos"}:
        driver_type = "nxos" if type_id == "cisco-nxos" else os.getenv("CISCO_DRIVER_TYPE", os.getenv("CISCO_DRIVER", "ios"))
        return {
            "name": f"{name} (Cisco {driver_type})",
            "connector_type": "cisco",
            "config": {
                "host": host,
                "username": os.getenv("CISCO_USER", "admin"),
                "password": os.getenv("CISCO_PASS", "Cisco123!"),
                "driver_type": driver_type,
            },
            "sync_mode": "on-demand",
            "sync_interval_minutes": 30,
        }

    if type_id == "juniper":
        return {
            "name": f"{name} (Juniper)",
            "connector_type": "juniper",
            "config": {
                "host": host,
                "username": os.getenv("JUNIPER_USER", "admin"),
                "password": os.getenv("JUNIPER_PASS", "Juniper123!"),
            },
            "sync_mode": "on-demand",
            "sync_interval_minutes": 30,
        }

    return None


def discover_devices(headers: dict[str, str]) -> list[dict]:
    res = requests.get(f"{API_BASE}/lab/containers", headers=headers)
    if res.status_code != 200:
        print(f"Could not fetch /lab/containers: {res.status_code} {res.text}")
        return []

    devices: list[dict] = []
    for container in res.json():
        if str(container.get("status", "")).lower() != "running":
            continue
        payload = to_connector_payload(container)
        if payload is not None:
            devices.append(payload)
    return devices


def main():
    print("=" * 60)
    print("  Deplyx Lab — Registering Mock Devices as Connectors")
    print("=" * 60)
    print()

    headers = get_auth_headers()
    print(f"Authenticated as {ADMIN_EMAIL}\n")

    devices = discover_devices(headers)
    print(f"Discovered {len(devices)} supported running lab device(s)\n")

    # Check existing connectors
    existing = requests.get(f"{API_BASE}/connectors", headers=headers)
    existing_names = set()
    if existing.status_code == 200:
        existing_names = {c["name"] for c in existing.json()}

    for device in devices:
        name = device["name"]
        if name in existing_names:
            print(f"  [skip] {name} — already registered")
            continue

        res = requests.post(
            f"{API_BASE}/connectors",
            json=device,
            headers=headers,
        )
        if res.status_code == 201:
            connector_id = res.json()["id"]
            print(f"  [✓] {name} — registered (id={connector_id})")
        else:
            print(f"  [✗] {name} — failed: {res.text}")

    print()
    print("All devices registered. You can now sync them via the UI or API:")
    print("  POST /api/v1/connectors/{id}/sync")
    print()


if __name__ == "__main__":
    main()
