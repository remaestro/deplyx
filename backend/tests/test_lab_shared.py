"""Unit tests for lab/shared modules."""

import sys
import pathlib
import threading
import time

import pytest

# Ensure lab/ is on the Python path so `from shared.state import ...` works
_lab_dir = str(pathlib.Path(__file__).resolve().parents[2] / "lab")
if _lab_dir not in sys.path:
    sys.path.insert(0, _lab_dir)


class TestDeviceState:
    def _make(self):
        from shared.state import DeviceState
        return DeviceState()

    def test_initial_state(self):
        ds = self._make()
        assert ds.ready is False
        assert ds.last_sync_at is None

    def test_set_get(self):
        ds = self._make()
        ds.set("hostname", "fw01")
        assert ds.get("hostname") == "fw01"

    def test_get_default(self):
        ds = self._make()
        assert ds.get("nonexistent", "fallback") == "fallback"

    def test_update_batch(self):
        ds = self._make()
        ds.update({"a": 1, "b": 2})
        assert ds.get("a") == 1
        assert ds.get("b") == 2

    def test_snapshot_is_isolated(self):
        ds = self._make()
        ds.set("k", "v")
        snap = ds.snapshot()
        snap["k"] = "changed"
        assert ds.get("k") == "v"

    def test_mark_ready(self):
        ds = self._make()
        ds.mark_ready()
        assert ds.ready is True

    def test_mark_synced(self):
        ds = self._make()
        ds.mark_synced()
        assert ds.last_sync_at is not None

    def test_as_dict(self):
        ds = self._make()
        ds.set("x", 1)
        ds.mark_ready()
        d = ds.as_dict()
        assert d["ready"] is True
        assert d["data"]["x"] == 1

    def test_thread_safety(self):
        ds = self._make()
        errors: list[str] = []

        def writer():
            for i in range(100):
                ds.set(f"key-{i}", i)

        def reader():
            for _ in range(100):
                try:
                    ds.snapshot()
                except Exception as e:
                    errors.append(str(e))

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert errors == []


class TestHealthServer:
    def test_starts_daemon_thread(self):
        from shared.state import DeviceState
        from shared.health_server import start_health_server

        ds = DeviceState()
        ds.mark_ready()
        t = start_health_server(ds, port=18081)
        assert isinstance(t, threading.Thread)
        assert t.daemon is True
        assert t.is_alive()

    def test_health_endpoint(self):
        import json
        import urllib.request

        from shared.state import DeviceState
        from shared.health_server import start_health_server

        ds = DeviceState()
        ds.mark_ready()
        start_health_server(ds, port=18082)
        time.sleep(0.1)  # let server start

        resp = urllib.request.urlopen("http://127.0.0.1:18082/health")
        body = json.loads(resp.read())
        assert body["status"] == "ok"
        assert body["ready"] is True

    def test_404_on_unknown_path(self):
        import urllib.request
        import urllib.error

        from shared.state import DeviceState
        from shared.health_server import start_health_server

        ds = DeviceState()
        start_health_server(ds, port=18083)
        time.sleep(0.1)

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen("http://127.0.0.1:18083/unknown")
        assert exc_info.value.code == 404
