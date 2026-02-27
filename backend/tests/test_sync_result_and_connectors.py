"""Unit tests for SyncResult and connector structure.

These tests validate SyncResult semantics and that all connectors have the
correct shape (methods, ID patterns, etc.) without connecting to real devices.
"""

import importlib
import inspect

import pytest

from app.connectors.base import SyncResult, BaseConnector


# ── SyncResult semantics ─────────────────────────────────────────────────

class TestSyncResultSemantics:
    def test_empty_is_synced(self):
        sr = SyncResult()
        sr.finalise()
        assert sr.status == "synced"

    def test_only_successes_stays_synced(self):
        sr = SyncResult()
        sr.record_success("a")
        sr.record_success("b")
        sr.finalise()
        assert sr.status == "synced"

    def test_mixed_becomes_partial(self):
        sr = SyncResult()
        sr.record_success("a")
        sr.record_failure("b", "err")
        sr.finalise()
        assert sr.status == "partial"

    def test_only_failures_becomes_error(self):
        sr = SyncResult()
        sr.record_failure("a", "err1")
        sr.record_failure("b", "err2")
        sr.finalise()
        assert sr.status == "error"

    def test_multiple_errors_accumulated(self):
        sr = SyncResult()
        sr.record_failure("x", "e1")
        sr.record_failure("x", "e2")
        sr.finalise()
        assert sr.failed["x"] == 2
        assert len(sr.errors) == 2

    def test_to_dict_structure(self):
        sr = SyncResult()
        sr.record_success("ok")
        sr.record_failure("bad", "oops")
        sr.finalise()
        d = sr.to_dict()
        assert isinstance(d, dict)
        assert d["status"] == "partial"
        assert d["synced"] == {"ok": 1}
        assert d["failed"] == {"bad": 1}
        assert any("oops" in e for e in d["errors"])


# ── Connector structure tests ─────────────────────────────────────────────

ALL_CONNECTOR_MODULES = [
    "app.connectors.fortinet",
    "app.connectors.paloalto",
    "app.connectors.checkpoint",
    "app.connectors.cisco",
    "app.connectors.juniper",
    "app.connectors.aruba_switch",
    "app.connectors.aruba_ap",
    "app.connectors.cisco_nxos",
    "app.connectors.cisco_router",
    "app.connectors.cisco_wlc",
    "app.connectors.vyos",
    "app.connectors.strongswan_vpn",
    "app.connectors.snort_ids",
    "app.connectors.openldap",
    "app.connectors.nginx_app",
    "app.connectors.postgres_app",
    "app.connectors.redis_app",
    "app.connectors.elasticsearch",
    "app.connectors.grafana",
    "app.connectors.prometheus",
]


def _find_connector_class(module_path: str) -> type:
    mod = importlib.import_module(module_path)
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if issubclass(obj, BaseConnector) and obj is not BaseConnector:
            return obj
    raise AssertionError(f"No BaseConnector subclass in {module_path}")


class TestAllConnectorsShape:
    @pytest.mark.parametrize("module_path", ALL_CONNECTOR_MODULES)
    def test_has_sync_method(self, module_path):
        cls = _find_connector_class(module_path)
        assert hasattr(cls, "sync"), f"{cls.__name__} missing sync()"

    @pytest.mark.parametrize("module_path", ALL_CONNECTOR_MODULES)
    def test_has_validate_change(self, module_path):
        cls = _find_connector_class(module_path)
        assert hasattr(cls, "validate_change")

    @pytest.mark.parametrize("module_path", ALL_CONNECTOR_MODULES)
    def test_has_simulate_change(self, module_path):
        cls = _find_connector_class(module_path)
        assert hasattr(cls, "simulate_change")

    @pytest.mark.parametrize("module_path", ALL_CONNECTOR_MODULES)
    def test_has_apply_change(self, module_path):
        cls = _find_connector_class(module_path)
        assert hasattr(cls, "apply_change")

    @pytest.mark.parametrize("module_path", ALL_CONNECTOR_MODULES)
    def test_is_base_connector_subclass(self, module_path):
        cls = _find_connector_class(module_path)
        assert issubclass(cls, BaseConnector)

    @pytest.mark.parametrize("module_path", ALL_CONNECTOR_MODULES)
    def test_sync_is_async(self, module_path):
        cls = _find_connector_class(module_path)
        assert inspect.iscoroutinefunction(cls.sync), f"{cls.__name__}.sync() is not async"


# ── Safe-ID utility (used in new connectors) ─────────────────────────────

class TestSafeIdUtility:
    """Verify _safe_id in new connectors sanitises correctly."""

    @pytest.mark.parametrize(
        "input_val,expected_substr",
        [
            ("hello world", "hello_world"),
            ("a/b/c", "a_b_c"),
            ("  spaces  ", "spaces"),
            ("clean", "clean"),
        ],
    )
    def test_safe_id(self, input_val, expected_substr):
        from app.connectors.aruba_switch import _safe_id  # any new connector
        result = _safe_id(input_val)
        assert expected_substr in result
        assert " " not in result

    def test_empty_returns_unknown(self):
        from app.connectors.aruba_switch import _safe_id
        assert _safe_id("   ") == "unknown"
