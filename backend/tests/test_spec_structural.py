"""Structural spec-compliance tests.

These tests verify that the codebase structurally matches the Deplyx spec
without requiring any external services (no DB, no Neo4j, no Redis).

They inspect module attributes, class hierarchies, function signatures, and
constant values.
"""

import importlib
import inspect
import pathlib
import re
import sys

# Ensure lab/ is on the Python path
_lab_dir = str(pathlib.Path(__file__).resolve().parents[2] / "lab")
if _lab_dir not in sys.path:
    sys.path.insert(0, _lab_dir)

import pytest


# ── §2  Interfaces / Protocols ────────────────────────────────────────────

class TestInterfacesModule:
    def _mod(self):
        return importlib.import_module("app.interfaces")

    def test_all_protocols_exist(self):
        mod = self._mod()
        expected = [
            "ImpactAnalyzer",
            "RiskEvaluator",
            "WorkflowRouter",
            "NotificationSender",
            "IGraphClient",
            "IChangeRepository",
            "IPolicyRepository",
            "IApprovalRepository",
            "IAuditRepository",
            "IAlertNotifier",
        ]
        for name in expected:
            assert hasattr(mod, name), f"Missing protocol: {name}"

    def test_igraph_client_methods(self):
        mod = self._mod()
        cls = getattr(mod, "IGraphClient")
        assert hasattr(cls, "merge_node")
        assert hasattr(cls, "create_relationship")

    def test_ichange_repository_methods(self):
        mod = self._mod()
        cls = getattr(mod, "IChangeRepository")
        assert hasattr(cls, "get")
        assert hasattr(cls, "set_stage")


# ── §3  Pipeline Error types ──────────────────────────────────────────────

class TestPipelineErrors:
    def test_transient_error_exists(self):
        from app.tasks.pipeline.errors import TransientError, PipelineError

        assert issubclass(TransientError, PipelineError)

    def test_change_not_found_error_exists(self):
        from app.tasks.pipeline.errors import ChangeNotFoundError, PipelineError

        assert issubclass(ChangeNotFoundError, PipelineError)


# ── §4  Governance errors ─────────────────────────────────────────────────

class TestGovernanceErrors:
    def test_policy_store_unavailable(self):
        from app.governance.errors import PolicyStoreUnavailableError, ThresholdArtifactError

        assert issubclass(PolicyStoreUnavailableError, ThresholdArtifactError)


# ── §5  SyncResult dataclass ─────────────────────────────────────────────

class TestSyncResult:
    def _cls(self):
        from app.connectors.base import SyncResult
        return SyncResult

    def test_initial_status(self):
        sr = self._cls()()
        assert sr.status == "synced"

    def test_record_success(self):
        sr = self._cls()()
        sr.record_success("devices")
        sr.record_success("devices")
        sr.record_success("interfaces")
        assert sr.synced["devices"] == 2
        assert sr.synced["interfaces"] == 1

    def test_record_failure_sets_partial(self):
        sr = self._cls()()
        sr.record_success("devices")
        sr.record_failure("interfaces", "timeout")
        sr.finalise()
        assert sr.status == "partial"
        assert sr.failed["interfaces"] == 1
        assert any("timeout" in e for e in sr.errors)

    def test_all_failures_set_error(self):
        sr = self._cls()()
        sr.record_failure("devices", "conn refused")
        sr.finalise()
        assert sr.status == "error"

    def test_to_dict_keys(self):
        sr = self._cls()()
        sr.record_success("x")
        sr.finalise()
        d = sr.to_dict()
        assert set(d.keys()) == {"status", "synced", "failed", "errors"}


# ── §6  AlertEvent dataclass ─────────────────────────────────────────────

class TestAlertEvent:
    def test_fields(self):
        from app.alerting.notifier import AlertEvent

        ae = AlertEvent(
            event_type="dead_letter",
            change_id=42,
            attempts=3,
            last_error="boom",
        )
        assert ae.event_type == "dead_letter"
        assert ae.change_id == 42
        assert ae.timestamp  # auto-populated


# ── §7  ALLOWED_REL_TYPES ────────────────────────────────────────────────

class TestAllowedRelTypes:
    def test_minimum_set(self):
        from app.graph.neo4j_client import ALLOWED_REL_TYPES

        must_have = {
            "HAS_INTERFACE", "HAS_RULE", "HOSTS", "HAS_IP", "PROTECTS",
            "CONNECTED_TO", "HAS_BGP_PEER", "HAS_VRF", "HAS_ROUTE",
            "HAS_VPN_TUNNEL", "HAS_WLAN", "HAS_AP", "SERVES_WLAN",
            "HAS_RADIO", "HAS_VHOST", "HAS_INDEX", "HAS_DATASOURCE",
            "HAS_SCRAPE_TARGET", "HAS_REPLICA", "PART_OF", "ROUTES_TO",
            "LOCATED_IN",
        }
        assert must_have.issubset(ALLOWED_REL_TYPES)

    def test_is_frozenset(self):
        from app.graph.neo4j_client import ALLOWED_REL_TYPES

        assert isinstance(ALLOWED_REL_TYPES, frozenset)


# ── §8  Display-name constants ───────────────────────────────────────────

class TestDisplayNameConstants:
    def _mod(self):
        return importlib.import_module("app.connectors.display_name")

    def test_vendor_constants(self):
        mod = self._mod()
        vendors = [
            "VENDOR_FORTINET", "VENDOR_PALO_ALTO", "VENDOR_CHECK_POINT",
            "VENDOR_CISCO", "VENDOR_JUNIPER", "VENDOR_ARUBA", "VENDOR_VYOS",
            "VENDOR_STRONGSWAN", "VENDOR_SNORT", "VENDOR_OPENLDAP",
            "VENDOR_NGINX", "VENDOR_POSTGRES", "VENDOR_REDIS",
            "VENDOR_ELASTICSEARCH", "VENDOR_GRAFANA", "VENDOR_PROMETHEUS",
        ]
        for v in vendors:
            assert hasattr(mod, v), f"Missing vendor constant: {v}"
            val = getattr(mod, v)
            assert isinstance(val, str) and len(val) > 0

    def test_function_constants(self):
        mod = self._mod()
        funcs = [
            "FUNCTION_FIREWALL", "FUNCTION_SWITCH", "FUNCTION_ROUTER",
            "FUNCTION_WLC", "FUNCTION_AP", "FUNCTION_VPN",
            "FUNCTION_IDS", "FUNCTION_DIRECTORY", "FUNCTION_PROXY",
            "FUNCTION_DATABASE", "FUNCTION_CACHE", "FUNCTION_SEARCH",
            "FUNCTION_MONITORING", "FUNCTION_METRICS",
        ]
        for f in funcs:
            assert hasattr(mod, f), f"Missing function constant: {f}"

    def test_builder_functions_exist(self):
        mod = self._mod()
        for fn_name in ["device", "interface", "rule", "ip_address", "application"]:
            assert callable(getattr(mod, fn_name, None)), f"Missing builder: {fn_name}"


class TestDisplayNameBuilders:
    def _mod(self):
        return importlib.import_module("app.connectors.display_name")

    def test_device_contains_emdash(self):
        mod = self._mod()
        result = mod.device(mod.VENDOR_FORTINET, mod.FUNCTION_FIREWALL, "fw01")
        assert "\u2014" in result  # em-dash

    def test_rule_contains_parent(self):
        mod = self._mod()
        parent = mod.device(mod.VENDOR_FORTINET, mod.FUNCTION_FIREWALL, "fw01")
        result = mod.rule("policy-100", parent)
        assert "policy-100" in result
        assert parent in result

    def test_ip_address_format(self):
        mod = self._mod()
        result = mod.ip_address("10.0.0.1")
        assert "10.0.0.1" in result

    def test_application_replaces_hyphens(self):
        mod = self._mod()
        result = mod.application("my-cool_app")
        assert "-" not in result
        assert "_" not in result


# ── §9  Connector CLASSES registry ───────────────────────────────────────

class TestConnectorRegistry:
    def test_all_21_types(self):
        from app.services.connector_service import CONNECTOR_CLASSES

        expected = {
            "paloalto", "fortinet", "cisco", "checkpoint", "juniper",
            "aruba-switch", "aruba-ap", "cisco-nxos", "cisco-ftd", "cisco-router",
            "cisco-wlc", "vyos", "strongswan", "snort", "openldap",
            "nginx", "postgres", "redis", "elasticsearch", "grafana",
            "prometheus",
        }
        assert expected == set(CONNECTOR_CLASSES.keys())

    def test_all_are_base_connector_subclasses(self):
        from app.connectors.base import BaseConnector
        from app.services.connector_service import CONNECTOR_CLASSES

        for name, cls in CONNECTOR_CLASSES.items():
            assert issubclass(cls, BaseConnector), f"{name} -> {cls} is not a BaseConnector"


# ── §10  Connector ID patterns ───────────────────────────────────────────

class TestConnectorIDPatterns:
    """Verify that each new connector's ID patterns use the correct prefix."""

    PATTERNS = {
        "aruba_switch": r"^ARUBA-SW-",
        "cisco_nxos": r"^NXOS-",
        "cisco_ftd": r"^FTD-",
        "cisco_router": r"^ROUTER-",
        "cisco_wlc": r"^WLC-",
        "aruba_ap": r"^ARUBA-AP-",
        "vyos": r"^VYOS-",
        "strongswan_vpn": r"^VPN-",
        "snort_ids": r"^IDS-",
        "openldap": r"^LDAP-",
        "nginx_app": r"^NGINX-",
        "postgres_app": r"^PG-",
        "redis_app": r"^REDIS-",
        "elasticsearch": r"^ES-",
        "grafana": r"^GRAFANA-",
        "prometheus": r"^PROM-",
    }

    @pytest.mark.parametrize("module_name,pattern", list(PATTERNS.items()))
    def test_device_id_prefix_in_source(self, module_name, pattern):
        """Inspect the connector source for the expected device ID prefix."""
        mod = importlib.import_module(f"app.connectors.{module_name}")
        source = inspect.getsource(mod)
        # The f-string prefix should appear literally
        prefix = pattern.replace("^", "").replace("-", "-")
        assert prefix.rstrip("-") in source, (
            f"Connector {module_name} does not contain the expected ID prefix '{prefix}'"
        )


# ── §11 ThresholdConfig ─────────────────────────────────────────────────

class TestThresholdConfig:
    def test_dataclass_fields(self):
        from app.governance.threshold_artifact import ThresholdConfig

        tc = ThresholdConfig(auto_approve_max=20, targeted_max=60, cab_min=61)
        assert tc.auto_approve_max == 20
        assert tc.targeted_max == 60
        assert tc.cab_min == 61


# ── §12 Connector model has last_sync_detail ─────────────────────────────

class TestConnectorModel:
    def test_last_sync_detail_column(self):
        from app.models.connector import Connector

        mapper = Connector.__table__
        col_names = {c.name for c in mapper.columns}
        assert "last_sync_detail" in col_names


# ── §13 Dead-letter task exists ──────────────────────────────────────────

class TestDeadLetterTask:
    def test_task_function_exists(self):
        from app.tasks.poll_dead_letter import poll_dead_letter

        assert callable(poll_dead_letter)

    def test_redis_constants(self):
        from app.tasks.poll_dead_letter import DEAD_LETTER_KEY, MAX_ATTEMPTS

        assert isinstance(DEAD_LETTER_KEY, str)
        assert MAX_ATTEMPTS >= 1


# ── §14 Reconcile task exists ────────────────────────────────────────────

class TestReconcileTask:
    def test_task_function_exists(self):
        from app.tasks.reconcile_graph_pg import reconcile_graph_pg

        assert callable(reconcile_graph_pg)

    def test_get_last_drift_count(self):
        from app.tasks.reconcile_graph_pg import get_last_drift_count

        assert isinstance(get_last_drift_count(), int)


# ── §15 Lab shared modules ──────────────────────────────────────────────

class TestLabSharedState:
    def test_device_state(self):
        from shared.state import DeviceState

        ds = DeviceState()
        assert ds.ready is False
        ds.set("hostname", "fw01")
        assert ds.get("hostname") == "fw01"
        ds.mark_ready()
        assert ds.ready is True

    def test_snapshot_is_copy(self):
        from shared.state import DeviceState

        ds = DeviceState()
        ds.set("k", "v")
        snap = ds.snapshot()
        snap["k"] = "changed"
        assert ds.get("k") == "v"

    def test_as_dict(self):
        from shared.state import DeviceState

        ds = DeviceState()
        ds.mark_ready()
        ds.mark_synced()
        d = ds.as_dict()
        assert d["ready"] is True
        assert d["last_sync_at"] is not None


class TestLabHealthServer:
    def test_start_returns_thread(self):
        import threading
        from shared.state import DeviceState
        from shared.health_server import start_health_server

        ds = DeviceState()
        t = start_health_server(ds, port=18080)
        assert isinstance(t, threading.Thread)
        assert t.daemon is True
        # Cleanup: no clean way to stop HTTPServer from here, but it's a
        # daemon thread so it'll die with the process.


# ── §16 Frontend STAGE_LABELS ────────────────────────────────────────────
# (Checked indirectly — we parse the TS source for the constant.)

class TestFrontendStageLabels:
    def test_stage_labels_in_source(self):
        import pathlib

        ts_path = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "changeStage.ts"
        if not ts_path.exists():
            pytest.skip("Frontend not available")
        source = ts_path.read_text()
        assert "STAGE_LABELS" in source
        for stage in ["fetching_data", "computing_impact", "scoring_risk", "routing_workflow", "finalised", "failed"]:
            assert stage in source, f"Missing stage '{stage}' in STAGE_LABELS"


# ── §17 Alembic migration chain ─────────────────────────────────────────

class TestAlembicMigrations:
    def test_0007_exists(self):
        import pathlib

        migration = (
            pathlib.Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "0007_add_last_sync_detail.py"
        )
        assert migration.exists(), "Migration 0007 not found"

    def test_0007_adds_column(self):
        import pathlib

        migration = (
            pathlib.Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "0007_add_last_sync_detail.py"
        )
        source = migration.read_text()
        assert "last_sync_detail" in source
        assert "connectors" in source


# ── §18 Fakes satisfy protocols ──────────────────────────────────────────

class TestFakesExist:
    def test_fake_graph_client(self):
        from tests.fakes.fake_graph_client import FakeGraphClient

        g = FakeGraphClient()
        assert hasattr(g, "merge_node")
        assert hasattr(g, "create_relationship")
        assert hasattr(g, "get_full_topology")

    def test_fake_repositories(self):
        from tests.fakes.fake_repositories import (
            FakeChangeRepository,
            FakePolicyRepository,
            FakeApprovalRepository,
            FakeAuditRepository,
        )
        assert callable(FakeChangeRepository)
        assert callable(FakePolicyRepository)
        assert callable(FakeApprovalRepository)
        assert callable(FakeAuditRepository)

    def test_fake_alert_notifier(self):
        from tests.fakes.fake_alert_notifier import FakeAlertNotifier

        n = FakeAlertNotifier()
        assert hasattr(n, "send")
        assert hasattr(n, "record")
