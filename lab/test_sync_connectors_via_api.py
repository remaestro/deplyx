#!/usr/bin/env python3
import json
import os
import time
import unittest
import urllib.error
import urllib.request

API_BASE = os.getenv("DEPLYX_API_BASE", "http://localhost:8000/api/v1")
API_HEALTH = API_BASE.replace("/api/v1", "/health")
ADMIN_EMAIL = os.getenv("DEPLYX_ADMIN_EMAIL", "debug2@deplyx.io")
ADMIN_PASSWORD = os.getenv("DEPLYX_ADMIN_PASSWORD", "Admin123!")

CONNECTOR_KEYS = [
    "fw-edge-01",
    "fw-dmz-01",
    "sec-gw-01",
    "rt-wan-01",
    "rt-core-01",
    "sw-core-01",
    "sw-dc-01",
    "sw-dist-01",
    "sw-access-01",
    "wlc-01",
    "ap-campus-01",
    "vpn-remote-01",
    "ids-dmz-01",
    "ldap-idm-01",
    "web-gw-01",
    "db-main-01",
    "cache-main-01",
    "search-obs-01",
    "grafana-obs-01",
    "prom-core-01",
]


def request_json(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: int = 30):
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.getcode(), res.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        payload = err.read().decode("utf-8")
        err.close()
        return err.code, payload


def wait_for_api_ready(timeout_seconds: int = 60) -> None:
    started = time.time()
    while time.time() - started < timeout_seconds:
        try:
            req = urllib.request.Request(API_HEALTH, method="GET")
            with urllib.request.urlopen(req, timeout=5) as res:
                if 200 <= res.getcode() < 300:
                    return
        except Exception:
            pass
        time.sleep(0.5)

    raise RuntimeError(f"API not ready at {API_HEALTH} after {timeout_seconds}s")


def login_headers() -> dict[str, str]:
    wait_for_api_ready()

    for attempt in range(1, 6):
        try:
            code, body = request_json(
                "POST",
                f"{API_BASE}/auth/login",
                {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=20,
            )
            if code == 200:
                token = json.loads(body).get("access_token")
                if token:
                    return {"Authorization": f"Bearer {token}"}
        except Exception:
            pass

        time.sleep(attempt)

    raise RuntimeError(f"Login failed for {ADMIN_EMAIL} after retries")


def list_connectors(headers: dict[str, str]) -> list[dict]:
    code, body = request_json("GET", f"{API_BASE}/connectors", headers=headers, timeout=30)
    if code != 200:
        raise RuntimeError(f"Unable to list connectors: {code} {body}")
    return json.loads(body)


def find_connector_by_key(connectors: list[dict], key: str) -> dict | None:
    for connector in connectors:
        name = str(connector.get("name", ""))
        host = str(connector.get("config", {}).get("host", ""))
        if key in name or key in host:
            return connector
    return None


class TestSyncConnectorsViaApi(unittest.TestCase):
    def test_sync_one_request_per_connector(self):
        headers = login_headers()
        connectors = list_connectors(headers)

        self.assertGreaterEqual(
            len(connectors),
            len(CONNECTOR_KEYS),
            f"Expected at least {len(CONNECTOR_KEYS)} connectors, got {len(connectors)}",
        )

        started = 0
        missing = []

        for key in CONNECTOR_KEYS:
            with self.subTest(connector_key=key):
                connector = find_connector_by_key(connectors, key)
                if not connector:
                    missing.append(key)
                    self.fail(f"Connector not found for key: {key}")

                connector_id = connector["id"]
                code, body = request_json(
                    "POST",
                    f"{API_BASE}/connectors/{connector_id}/sync",
                    headers=headers,
                    timeout=20,
                )
                self.assertIn(
                    code,
                    {200, 201, 202},
                    f"Sync failed for {key} (id={connector_id}): {code} {body}",
                )
                started += 1

                time.sleep(0.15)

        print(f"sync_requests_started={started}")
        print(f"missing_connectors={missing}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
