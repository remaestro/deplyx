#!/usr/bin/env python3
import json
import os
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = LAB_DIR / "docker-compose.yml"
API_BASE = os.getenv("DEPLYX_API_BASE", "http://localhost:8000/api/v1")
ADMIN_EMAIL = os.getenv("DEPLYX_ADMIN_EMAIL", "labadmin@deplyx.io")
ADMIN_PASSWORD = os.getenv("DEPLYX_ADMIN_PASSWORD", "LabAdmin123!")
START_TIMEOUT_SECONDS = int(os.getenv("LAB_START_TIMEOUT", "300"))
POLL_INTERVAL_SECONDS = 3

SUPPORTED_TYPE_IDS = {"fortinet", "paloalto", "checkpoint", "cisco-ios", "cisco-nxos", "juniper"}


def run_compose(args: list[str]) -> str:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), *args]
    res = subprocess.run(cmd, cwd=LAB_DIR, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}")
    return res.stdout.strip()


def request_json(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, str]:
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.getcode(), res.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        payload = err.read().decode("utf-8")
        err.close()
        return err.code, payload


def get_auth_headers() -> dict[str, str]:
    request_json(
        "POST",
        f"{API_BASE}/auth/register",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "role": "admin"},
    )
    code, body = request_json(
        "POST",
        f"{API_BASE}/auth/login",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if code != 200:
        raise RuntimeError(f"Login failed: {code} {body}")
    token = json.loads(body)["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
            "config": {"host": host, "api_token": os.getenv("FORTINET_API_TOKEN", "fg-lab-token-001"), "verify_ssl": False},
            "sync_mode": "on-demand",
            "sync_interval_minutes": 30,
        }

    if type_id == "paloalto":
        return {
            "name": f"{name} (Palo Alto)",
            "connector_type": "paloalto",
            "config": {"host": host, "api_key": os.getenv("PALOALTO_API_KEY", "pa-lab-apikey-001"), "verify_ssl": False},
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


def wait_for_all_lab_services_running():
    expected = set(run_compose(["config", "--services"]).splitlines())
    expected = {s.strip() for s in expected if s.strip()}
    if not expected:
        raise RuntimeError("No lab services found in docker-compose")

    run_compose(["up", "-d", "--remove-orphans"])

    deadline = time.time() + START_TIMEOUT_SECONDS
    while time.time() < deadline:
        running = set(run_compose(["ps", "--services", "--status", "running"]).splitlines())
        running = {s.strip() for s in running if s.strip()}
        if expected.issubset(running):
            return
        time.sleep(POLL_INTERVAL_SECONDS)

    running = set(run_compose(["ps", "--services", "--status", "running"]).splitlines())
    missing = sorted(expected - {s.strip() for s in running if s.strip()})
    raise RuntimeError(f"Not all lab services are running. Missing: {missing}")


def discover_lab_devices_from_docker() -> list[dict]:
    ids_output = run_compose(["ps", "-q"])
    container_ids = [line.strip() for line in ids_output.splitlines() if line.strip()]
    devices: list[dict] = []

    for container_id in container_ids:
        inspect = subprocess.run(
            ["docker", "inspect", container_id],
            cwd=LAB_DIR,
            text=True,
            capture_output=True,
            check=False,
        )
        if inspect.returncode != 0:
            continue

        data = json.loads(inspect.stdout)[0]
        labels = data.get("Config", {}).get("Labels", {}) or {}
        if labels.get("deplyx.lab") != "true":
            continue

        type_id = labels.get("deplyx.type", "")
        if type_id not in SUPPORTED_TYPE_IDS:
            continue

        networks = data.get("NetworkSettings", {}).get("Networks", {}) or {}
        ip = ""
        for net in networks.values():
            candidate = net.get("IPAddress", "")
            if candidate:
                ip = candidate
                break
        if not ip:
            continue

        devices.append(
            {
                "id": data.get("Name", "").lstrip("/"),
                "name": data.get("Name", "").lstrip("/"),
                "type_id": type_id,
                "status": data.get("State", {}).get("Status", ""),
                "ip": ip,
            }
        )

    return devices


class TestCreateConnectorPerLabDevice(unittest.TestCase):
    def test_create_one_connector_for_each_lab_device(self):
        wait_for_all_lab_services_running()
        headers = get_auth_headers()

        code, body = request_json("GET", f"{API_BASE}/connectors", headers=headers)
        self.assertEqual(code, 200, f"Could not list connectors: {code} {body}")
        for connector in json.loads(body):
            del_code, del_body = request_json("DELETE", f"{API_BASE}/connectors/{connector['id']}", headers=headers)
            self.assertIn(del_code, {200, 204}, f"Delete failed for {connector['id']}: {del_code} {del_body}")

        containers = discover_lab_devices_from_docker()

        running_supported_payloads = []
        for container in containers:
            if str(container.get("status", "")).lower() != "running":
                continue
            payload = to_connector_payload(container)
            if payload is not None:
                running_supported_payloads.append(payload)

        self.assertGreater(len(running_supported_payloads), 0, "No running supported lab devices discovered from Docker")

        created_names = []
        for payload in running_supported_payloads:
            create_code, create_body = request_json("POST", f"{API_BASE}/connectors", payload, headers=headers)
            self.assertEqual(create_code, 201, f"Create failed for {payload['name']}: {create_code} {create_body}")
            created_names.append(payload["name"])

        code, body = request_json("GET", f"{API_BASE}/connectors", headers=headers)
        self.assertEqual(code, 200, f"Could not re-list connectors: {code} {body}")
        listed = json.loads(body)
        listed_names = {c.get("name") for c in listed}

        self.assertEqual(len(listed), len(running_supported_payloads))
        self.assertTrue(set(created_names).issubset(listed_names))


if __name__ == "__main__":
    unittest.main(verbosity=2)
