#!/usr/bin/env python3
"""
Deplyx Lab — build-topology.py
===============================
Spins up the core 5-device lab topology and registers each device as a
connector in the running deplyx backend.

Usage (from the repo root):
    cd /path/to/deplyx
    # 1. Make sure the main deplyx stack is up:
    docker compose up -d
    # 2. Run this script:
    python lab/build-topology.py

What it does:
    1. Starts the 5 mock network containers (fw-dc1-01, pa-dc1-01,
       cp-mgmt-01, sw-dc1-core, sw-dc2-core) using docker compose.
    2. Waits until each container's service port is reachable.
    3. Registers / updates each device as a connector via the deplyx REST API.
    4. Triggers an initial sync on each connector.

Environment overrides (optional):
    DEPLYX_API     base URL of the deplyx API   (default: http://localhost:8000)
    DEPLYX_EMAIL   admin email                  (default: admin@deplyx.io)
    DEPLYX_PASS    admin password               (default: Admin123!)
    LAB_DIR        path to this lab/ directory  (default: auto-detected)
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEPLYX_API   = os.getenv("DEPLYX_API",   "http://localhost:8000")
ADMIN_EMAIL  = os.getenv("DEPLYX_EMAIL", "admin@deplyx.io")
ADMIN_PASS   = os.getenv("DEPLYX_PASS",  "Admin123!")
LAB_DIR      = Path(os.getenv("LAB_DIR", Path(__file__).parent))
HTTP_TIMEOUT = int(os.getenv("DEPLYX_HTTP_TIMEOUT", "30"))
HTTP_RETRIES = int(os.getenv("DEPLYX_HTTP_RETRIES", "3"))

SUPPORTED_TYPE_IDS = {"fortinet", "paloalto", "checkpoint", "cisco-ios", "cisco-nxos", "juniper"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

try:
    import urllib.request

    def _http(method: str, path: str, data: dict | None = None, token: str | None = None) -> tuple[int, dict]:
        url = f"{DEPLYX_API}/api/v1{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        for attempt in range(1, max(1, HTTP_RETRIES) + 1):
            try:
                with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as e:
                try:
                    err_body = json.loads(e.read())
                except Exception:
                    err_body = {"error": str(e)}
                return e.code, err_body
            except (TimeoutError, urllib.error.URLError) as e:
                if attempt >= max(1, HTTP_RETRIES):
                    return 503, {"error": f"Request failed after {attempt} attempt(s): {e}"}
                time.sleep(min(2 * attempt, 5))

except ImportError:
    def _http(*args, **kwargs):  # type: ignore
        raise RuntimeError("urllib not available")


def _log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def _ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}", flush=True)


def _warn(msg: str) -> None:
    print(f"  \033[33m⚠\033[0m {msg}", flush=True)


def _err(msg: str) -> None:
    print(f"  \033[31m✗\033[0m {msg}", flush=True)


def _header(msg: str) -> None:
    print(f"\n\033[1m{msg}\033[0m", flush=True)


def _device_from_lab_container(container: dict[str, Any]) -> dict[str, Any] | None:
    type_id = container.get("type_id", "")
    host = container.get("ip", "")
    name = container.get("name", container.get("id", "lab-device"))
    if type_id not in SUPPORTED_TYPE_IDS:
        return None
    if not host:
        return None

    if type_id == "fortinet":
        return {
            "name": f"{name} (Fortinet)",
            "connector_type": "fortinet",
            "host": host,
            "probe_port": 443,
            "config": {
                "host": host,
                "api_token": os.getenv("FORTINET_API_TOKEN", "fg-lab-token-001"),
                "verify_ssl": False,
            },
            "sync_interval_minutes": 30,
        }

    if type_id == "paloalto":
        return {
            "name": f"{name} (Palo Alto)",
            "connector_type": "paloalto",
            "host": host,
            "probe_port": 443,
            "config": {
                "host": host,
                "api_key": os.getenv("PALOALTO_API_KEY", "pa-lab-apikey-001"),
                "verify_ssl": False,
            },
            "sync_interval_minutes": 30,
        }

    if type_id == "checkpoint":
        return {
            "name": f"{name} (Check Point)",
            "connector_type": "checkpoint",
            "host": host,
            "probe_port": 443,
            "config": {
                "host": host,
                "username": os.getenv("CHECKPOINT_USER", "admin"),
                "password": os.getenv("CHECKPOINT_PASS", "Cp@ssw0rd!"),
                "verify_ssl": False,
            },
            "sync_interval_minutes": 60,
        }

    if type_id in {"cisco-ios", "cisco-nxos"}:
        driver_type = "nxos" if type_id == "cisco-nxos" else os.getenv("CISCO_DRIVER_TYPE", os.getenv("CISCO_DRIVER", "ios"))
        return {
            "name": f"{name} (Cisco {driver_type})",
            "connector_type": "cisco",
            "host": host,
            "probe_port": 22,
            "config": {
                "host": host,
                "username": os.getenv("CISCO_USER", "admin"),
                "password": os.getenv("CISCO_PASS", "Cisco123!"),
                "driver_type": driver_type,
            },
            "sync_interval_minutes": 30,
        }

    if type_id == "juniper":
        return {
            "name": f"{name} (Juniper)",
            "connector_type": "juniper",
            "host": host,
            "probe_port": 22,
            "config": {
                "host": host,
                "username": os.getenv("JUNIPER_USER", "admin"),
                "password": os.getenv("JUNIPER_PASS", "Juniper123!"),
            },
            "sync_interval_minutes": 30,
        }

    return None


def discover_devices(token: str) -> list[dict[str, Any]]:
    _header("Step 2 — Discovering lab devices from /lab/containers")
    status, body = _http("GET", "/lab/containers", token=token)
    if status != 200 or not isinstance(body, list):
        _warn(f"Unable to read /lab/containers ({status}) — no devices discovered")
        return []

    devices: list[dict[str, Any]] = []
    for c in body:
        if str(c.get("status", "")).lower() != "running":
            continue
        device = _device_from_lab_container(c)
        if device is not None:
            devices.append(device)

    if not devices:
        _warn("No supported running lab devices discovered")
    else:
        _ok(f"Discovered {len(devices)} supported lab device(s)")

    return devices


# ---------------------------------------------------------------------------
# Step 1: Start containers
# ---------------------------------------------------------------------------

def start_containers() -> None:
    _header("Step 1 — Starting lab stack")
    compose_file = LAB_DIR / "docker-compose.yml"
    if not compose_file.exists():
        _err(f"docker-compose.yml not found at {compose_file}")
        sys.exit(1)

    cmd = [
        "docker", "compose",
        "-f", str(compose_file),
        "up", "-d", "--build",
    ]

    _log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        _err("docker compose up failed — see output above")
        sys.exit(1)
    _ok("Containers started (or already running)")


# ---------------------------------------------------------------------------
# Step 2: Wait for ports
# ---------------------------------------------------------------------------

def _tcp_ready(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError, socket.timeout):
        return False


def wait_for_devices(devices: list[dict[str, Any]], max_wait: int = 60) -> None:
    _header("Step 3 — Waiting for devices to be reachable")
    deadline = time.time() + max_wait
    pending = list(devices)

    while pending and time.time() < deadline:
        still_pending = []
        for d in pending:
            if _tcp_ready(d["host"], d["probe_port"]):
                _ok(f"{d['name']} reachable at {d['host']}:{d['probe_port']}")
            else:
                still_pending.append(d)
        pending = still_pending
        if pending:
            time.sleep(3)

    for d in pending:
        _warn(f"{d['name']} NOT reachable at {d['host']}:{d['probe_port']} — will register anyway")


# ---------------------------------------------------------------------------
# Step 3: Authenticate against deplyx API
# ---------------------------------------------------------------------------

def authenticate() -> str:
    _header("Step 2 — Authenticating with deplyx API")

    # Try login first
    status, body = _http("POST", "/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if status == 200:
        token = body.get("access_token", "")
        _ok(f"Logged in as {ADMIN_EMAIL}")
        return token

    # Fall back to register (first-run)
    if status in (401, 404):
        _log(f"Login failed ({status}), attempting registration...")
        status, body = _http("POST", "/auth/register", {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASS,
            "role": "admin",
        })
        if status in (200, 201):
            token = body.get("access_token", "")
            _ok(f"Registered and logged in as {ADMIN_EMAIL}")
            return token

    _err(f"Authentication failed: {status} — {body}")
    _err(f"Make sure the deplyx backend is running at {DEPLYX_API}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Step 4: Register connectors
# ---------------------------------------------------------------------------

def register_connectors(token: str, devices: list[dict[str, Any]]) -> list[int]:
    _header("Step 4 — Registering connectors")

    # List existing connectors to avoid duplicates
    _, existing_list = _http("GET", "/connectors", token=token)
    existing = {c["name"]: c for c in (existing_list if isinstance(existing_list, list) else [])}

    connector_ids = []
    for d in devices:
        payload = {
            "name": d["name"],
            "connector_type": d["connector_type"],
            "config": d["config"],
            "sync_mode": "on-demand",
            "sync_interval_minutes": d.get("sync_interval_minutes", 60),
        }

        if d["name"] in existing:
            conn_id = existing[d["name"]]["id"]
            status, body = _http("PUT", f"/connectors/{conn_id}", payload, token=token)
            if status == 200:
                _ok(f"Updated connector: {d['name']} (id={conn_id})")
            else:
                _warn(f"Update failed for {d['name']}: {status} — {body}")
        else:
            status, body = _http("POST", "/connectors", payload, token=token)
            if status == 201:
                conn_id = body["id"]
                _ok(f"Created connector: {d['name']} (id={conn_id})")
            else:
                _warn(f"Create failed for {d['name']}: {status} — {body}")
                continue

        connector_ids.append(conn_id)

    return connector_ids


# ---------------------------------------------------------------------------
# Step 5: Initial sync
# ---------------------------------------------------------------------------

def initial_sync(token: str, connector_ids: list[int]) -> None:
    _header("Step 5 — Triggering initial sync on each connector")
    for conn_id in connector_ids:
        status, body = _http("POST", f"/connectors/{conn_id}/sync", token=token)
        vendor = body.get("vendor", f"connector-{conn_id}")
        sync_status = body.get("status", "?")
        synced = body.get("synced", {})
        if status == 200 and sync_status == "synced":
            _ok(f"[{conn_id}] {vendor}: synced {synced}")
        elif status == 200 and sync_status == "error":
            _warn(f"[{conn_id}] {vendor}: sync error — {body.get('error', '')}")
        else:
            _warn(f"[{conn_id}] HTTP {status} — {body}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("\n" + "=" * 60)
    print("  Deplyx Lab — build-topology")
    print("=" * 60)
    print(f"  API:   {DEPLYX_API}")
    print(f"  User:  {ADMIN_EMAIL}")
    print(f"  Lab:   {LAB_DIR}")

    start_containers()
    token = authenticate()
    devices = discover_devices(token)
    wait_for_devices(devices)
    ids = register_connectors(token, devices)
    initial_sync(token, ids)

    _header("Done")
    print(f"\n  {len(ids)} connectors registered and synced.")
    print(f"  Open {DEPLYX_API.replace('8000','5173')} to see the topology.\n")


if __name__ == "__main__":
    main()
