#!/usr/bin/env python3
import json
import os
import subprocess
import time
import unittest
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = LAB_DIR / "docker-compose.yml"
START_TIMEOUT_SECONDS = int(os.getenv("LAB_START_TIMEOUT", "300"))
POLL_INTERVAL_SECONDS = 3


def run_compose(args: list[str]) -> str:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), *args]
    res = subprocess.run(cmd, cwd=LAB_DIR, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}")
    return res.stdout.strip()


def get_expected_services() -> set[str]:
    output = run_compose(["config", "--services"])
    return {line.strip() for line in output.splitlines() if line.strip()}


def get_running_services() -> set[str]:
    output = run_compose(["ps", "--services", "--status", "running"])
    return {line.strip() for line in output.splitlines() if line.strip()}


class TestSpawnAllLabDevices(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        if os.getenv("LAB_TEST_KEEP_UP", "0") == "1":
            return
        run_compose(["down", "--remove-orphans"])

    def test_spawn_all_lab_devices(self):
        expected = get_expected_services()
        self.assertGreater(len(expected), 0, "No services found in lab/docker-compose.yml")

        run_compose(["up", "-d", "--remove-orphans"])

        deadline = time.time() + START_TIMEOUT_SECONDS
        while time.time() < deadline:
            running = get_running_services()
            if expected.issubset(running):
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        else:
            running = get_running_services()
            missing = sorted(expected - running)
            self.fail(
                "Not all lab devices started within timeout. "
                f"Missing: {missing}; Running: {sorted(running)}"
            )

        ps_json = run_compose(["ps", "--format", "json"])
        lines = [line for line in ps_json.splitlines() if line.strip()]
        containers = [json.loads(line) for line in lines]
        states = {c.get("Service"): c.get("State") for c in containers}
        for service in sorted(expected):
            self.assertEqual(states.get(service), "running", f"Service {service} is not running")


if __name__ == "__main__":
    unittest.main(verbosity=2)
