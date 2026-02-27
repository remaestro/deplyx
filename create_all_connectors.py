#!/usr/bin/env python3
"""Create one connector per lab device via the deplyx API.

Uses static IPs from lab/docker-compose.yml — no Lab API dependency.
Covers all 20 device types.

Usage:
  python3 create_all_connectors.py                          # local
  DEPLYX_API=http://167.86.104.86/api/v1 python3 create_all_connectors.py  # VPS
"""

import json
import os
import sys
import urllib.error
import urllib.request

BACKEND = os.getenv("DEPLYX_API", "http://localhost:8000/api/v1")
EMAIL = os.getenv("DEPLYX_EMAIL", "labadmin@deplyx.io")
PASSWORD = os.getenv("DEPLYX_PASSWORD", "LabAdmin123!")

# ── All 20 lab devices: (name, connector_type, ip, config) ──────────────────
DEVICES = [
    # Firewalls
    ("fw-edge-01",     "fortinet",     "10.100.0.10", {"host": "10.100.0.10", "api_token": "fg-lab-token-001", "verify_ssl": False}),
    ("fw-dmz-01",      "paloalto",     "10.100.0.11", {"host": "10.100.0.11", "api_key": "pa-lab-apikey-001", "verify_ssl": False}),
    ("sec-gw-01",      "checkpoint",   "10.100.0.12", {"host": "10.100.0.12", "username": "admin", "password": "Cp@ssw0rd!", "verify_ssl": False}),
    # Switches
    ("sw-core-01",     "cisco",        "10.100.0.20", {"host": "10.100.0.20", "username": "admin", "password": "Cisco123!", "driver_type": "ios"}),
    ("sw-dist-01",     "juniper",      "10.100.0.21", {"host": "10.100.0.21", "username": "admin", "password": "Juniper123!"}),
    ("sw-dc-01",       "cisco-nxos",   "10.100.0.22", {"host": "10.100.0.22", "username": "admin", "password": "Cisco123!"}),
    ("sw-access-01",   "aruba-switch", "10.100.0.23", {"host": "10.100.0.23", "username": "admin", "password": "Aruba123!"}),
    # Routers
    ("rt-wan-01",      "cisco-router", "10.100.0.30", {"host": "10.100.0.30", "username": "admin", "password": "Cisco123!"}),
    ("rt-core-01",     "vyos",         "10.100.0.31", {"host": "10.100.0.31", "username": "vyos", "password": "VyOS123!"}),
    # Wireless
    ("wlc-01",         "cisco-wlc",    "10.100.0.40", {"host": "10.100.0.40", "username": "admin", "password": "Wireless123!"}),
    ("ap-campus-01",   "aruba-ap",     "10.100.0.41", {"host": "10.100.0.41", "username": "admin", "password": "Aruba123!"}),
    # Security
    ("vpn-remote-01",  "strongswan",   "10.100.0.50", {"host": "10.100.0.50", "username": "admin", "password": "VPN123!"}),
    ("ids-dmz-01",     "snort",        "10.100.0.51", {"host": "10.100.0.51", "username": "admin", "password": "Snort123!"}),
    ("ldap-idm-01",    "openldap",     "10.100.0.52", {"host": "10.100.0.52", "username": "admin", "password": "LDAP123!"}),
    # Applications
    ("web-gw-01",      "nginx",        "10.100.0.60", {"host": "10.100.0.60", "username": "admin", "password": "App123!"}),
    ("db-main-01",     "postgres",     "10.100.0.61", {"host": "10.100.0.61", "username": "admin", "password": "App123!"}),
    ("cache-main-01",  "redis",        "10.100.0.62", {"host": "10.100.0.62", "username": "admin", "password": "App123!"}),
    ("search-obs-01",  "elasticsearch","10.100.0.63", {"host": "10.100.0.63", "username": "admin", "password": "App123!"}),
    ("grafana-obs-01", "grafana",      "10.100.0.64", {"host": "10.100.0.64", "username": "admin", "password": "App123!"}),
    ("prom-core-01",   "prometheus",   "10.100.0.65", {"host": "10.100.0.65", "username": "admin", "password": "App123!"}),
]


def http(method: str, url: str, body=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def main():
    print(f"Backend: {BACKEND}")
    print(f"User:    {EMAIL}\n")

    # Register + login
    http("POST", f"{BACKEND}/auth/register", {"email": EMAIL, "password": PASSWORD, "role": "admin"})
    code, body = http("POST", f"{BACKEND}/auth/login", {"email": EMAIL, "password": PASSWORD})
    if code != 200:
        print(f"Login failed: {code} {body}")
        sys.exit(1)
    auth = {"Authorization": f"Bearer {body['access_token']}"}
    print("Authenticated ✓\n")

    # Create connectors from static device list
    created = skipped = failed = 0
    for name, connector_type, ip, config in DEVICES:
        payload = {
            "name": f"{name} ({connector_type})",
            "connector_type": connector_type,
            "config": config,
            "sync_mode": "on-demand",
            "sync_interval_minutes": 30,
        }
        code, resp = http("POST", f"{BACKEND}/connectors", payload, auth)
        if code in (200, 201):
            print(f"  [✓] {payload['name']}")
            created += 1
        elif code == 409:
            print(f"  [skip] {payload['name']} (already exists)")
            skipped += 1
        else:
            detail = resp.get("detail", resp)
            print(f"  [✗] {payload['name']}  → {code}: {detail}")
            failed += 1

    print(f"\nDone: {created} created, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
