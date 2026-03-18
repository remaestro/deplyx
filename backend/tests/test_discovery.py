import pytest
from httpx import AsyncClient

from app.services import discovery_service


async def _register_admin(client: AsyncClient, email: str = "discovery-admin@deplyx.io") -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Admin123!", "role": "admin"},
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Admin123!"},
    )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_discovery_session_persists_results(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register_admin(client, email="discovery-persist-admin@deplyx.io")

    async def fake_probe_targets(targets, ports, timeout_seconds):
        assert [target.host for target in targets] == ["192.168.1.10", "192.168.1.2", "192.168.1.1"]
        assert ports == [22, 443]
        assert timeout_seconds == 4
        return [
            {
                "host": "192.168.1.10",
                "name_hint": None,
                "source_kind": "target",
                "status": "reachable",
                "selected_connector_type": None,
                "suggested_connector_types": ["cisco", "juniper"],
                "probe_detail": {"ports": [{"port": 22, "open": True, "error": None}]},
                "facts": {"open_ports": [22], "ssh_banner": "SSH-2.0-OpenSSH_9.0", "http": [], "snmp_port_open": False},
                "classification_reasons": ["SSH is reachable but no vendor-specific fingerprint matched"],
                "error": None,
            },
            {
                "host": "192.168.1.2",
                "name_hint": "fw-edge-01",
                "source_kind": "inventory",
                "status": "reachable",
                "selected_connector_type": "fortinet",
                "suggested_connector_types": ["fortinet"],
                "probe_detail": {"ports": [{"port": 443, "open": True, "error": None}]},
                "facts": {"open_ports": [443], "ssh_banner": None, "http": [{"url": "https://192.168.1.2:443/", "status": 200, "server": "FortiGate", "body_snippet": "Fortinet"}], "snmp_port_open": False},
                "classification_reasons": ["inventory declared connector_type=fortinet"],
                "error": None,
            },
            {
                "host": "192.168.1.1",
                "name_hint": None,
                "source_kind": "cidr",
                "status": "unreachable",
                "selected_connector_type": None,
                "suggested_connector_types": [],
                "probe_detail": {"ports": [{"port": 22, "open": False, "error": "timed out"}]},
                "facts": {"open_ports": [], "ssh_banner": None, "http": [], "snmp_port_open": False},
                "classification_reasons": ["No classification rule matched yet"],
                "error": "No known discovery port responded",
            },
        ]

    monkeypatch.setattr(discovery_service, "_probe_targets", fake_probe_targets)

    created = await client.post(
        "/api/v1/discovery/sessions",
        json={
            "name": "prod discovery",
            "targets": ["192.168.1.10"],
            "cidrs": ["192.168.1.0/30"],
            "inventory": [
                {
                    "host": "192.168.1.2",
                    "name": "fw-edge-01",
                    "connector_type": "fortinet",
                    "metadata": {"site": "dc1"},
                }
            ],
            "ports": [22, 443],
            "timeout_seconds": 4,
        },
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "completed"
    assert body["target_count"] == 3
    assert body["summary"]["reachable_targets"] == 2
    assert body["summary"]["selected_connector_types"] == {"fortinet": 1}
    assert len(body["results"]) == 3

    session_id = body["id"]

    fetched = await client.get(f"/api/v1/discovery/sessions/{session_id}", headers=headers)
    assert fetched.status_code == 200
    fetched_body = fetched.json()
    assert fetched_body["name"] == "prod discovery"
    assert fetched_body["input_payload"]["targets"] == ["192.168.1.10"]
    assert fetched_body["input_payload"]["cidrs"] == ["192.168.1.0/30"]
    assert fetched_body["results"][1]["selected_connector_type"] == "fortinet"

    results = await client.get(f"/api/v1/discovery/sessions/{session_id}/results", headers=headers)
    assert results.status_code == 200
    assert [item["host"] for item in results.json()] == ["192.168.1.10", "192.168.1.2", "192.168.1.1"]


@pytest.mark.asyncio
async def test_create_discovery_session_rejects_empty_input(client: AsyncClient) -> None:
    headers = await _register_admin(client, email="discovery-empty-admin@deplyx.io")

    response = await client.post(
        "/api/v1/discovery/sessions",
        json={"name": "empty discovery"},
        headers=headers,
    )
    assert response.status_code == 422
    assert "At least one of targets, cidrs, or inventory must be provided" in response.text


@pytest.mark.asyncio
async def test_create_discovery_session_rejects_large_cidr(client: AsyncClient) -> None:
    headers = await _register_admin(client, email="discovery-cidr-admin@deplyx.io")

    response = await client.post(
        "/api/v1/discovery/sessions",
        json={"cidrs": ["10.0.0.0/23"]},
        headers=headers,
    )
    assert response.status_code == 400
    assert "limit is 256" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_discovery_session_uses_expanded_default_ports(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register_admin(client, email="discovery-default-ports@deplyx.io")

    async def fake_probe_targets(targets, ports, timeout_seconds):
        assert ports == [22, 80, 161, 389, 443, 636, 3000, 5432, 6379, 8080, 8443, 9090, 9200]
        return [
            {
                "host": "192.168.1.50",
                "name_hint": None,
                "source_kind": "target",
                "status": "unreachable",
                "selected_connector_type": None,
                "suggested_connector_types": [],
                "probe_detail": {"ports": []},
                "facts": {
                    "open_ports": [],
                    "ssh_banner": None,
                    "http": [],
                    "redis": None,
                    "postgres": None,
                    "ldap": None,
                    "snmp_probe": None,
                    "management_apis": {},
                    "evidence": {
                        "reachable": False,
                        "service_detected": False,
                        "ssh_manageable": False,
                        "api_manageable": False,
                        "snmp_identified": False,
                    },
                },
                "classification_reasons": ["No classification rule matched yet"],
                "error": "No known discovery probe responded",
            }
        ]

    monkeypatch.setattr(discovery_service, "_probe_targets", fake_probe_targets)

    response = await client.post(
        "/api/v1/discovery/sessions",
        json={"targets": ["192.168.1.50"]},
        headers=headers,
    )
    assert response.status_code == 201


def test_classify_target_detects_redis_from_protocol_probe() -> None:
    target = discovery_service.PreparedTarget(host="10.0.0.15", source_kind="target")
    suggestions, selected, reasons = discovery_service._classify_target(
        target,
        {
            "open_ports": [6379],
            "ssh_banner": None,
            "http": [],
            "redis": {"status": "detected", "message": "+PONG"},
            "postgres": None,
            "snmp_probe": {"status": "not_implemented"},
        },
    )

    assert suggestions == ["redis"]
    assert selected == "redis"
    assert "Redis protocol probe succeeded" in reasons


def test_classify_target_detects_postgres_from_protocol_probe() -> None:
    target = discovery_service.PreparedTarget(host="10.0.0.16", source_kind="target")
    suggestions, selected, reasons = discovery_service._classify_target(
        target,
        {
            "open_ports": [5432],
            "ssh_banner": None,
            "http": [],
            "redis": None,
            "postgres": {"status": "detected", "ssl_supported": True},
            "snmp_probe": {"status": "not_implemented"},
        },
    )

    assert suggestions == ["postgres"]
    assert selected == "postgres"
    assert "PostgreSQL protocol probe succeeded" in reasons


def test_classify_target_detects_openldap_from_ldap_probe() -> None:
    target = discovery_service.PreparedTarget(host="10.0.0.17", source_kind="target")
    suggestions, selected, reasons = discovery_service._classify_target(
        target,
        {
            "open_ports": [389],
            "ssh_banner": None,
            "http": [],
            "redis": None,
            "postgres": None,
            "ldap": {"status": "detected", "port": 389, "result_code": 0},
            "snmp_probe": None,
            "management_apis": {},
        },
    )

    assert suggestions == ["openldap"]
    assert selected == "openldap"
    assert "LDAP bind probe succeeded" in reasons


def test_classify_target_detects_fortinet_from_management_api_probe() -> None:
    target = discovery_service.PreparedTarget(host="10.0.0.18", source_kind="target")
    suggestions, selected, reasons = discovery_service._classify_target(
        target,
        {
            "open_ports": [443],
            "ssh_banner": None,
            "http": [],
            "redis": None,
            "postgres": None,
            "ldap": None,
            "snmp_probe": None,
            "management_apis": {"fortinet": {"status": "detected", "port": 443, "status_code": 401}},
        },
    )

    assert suggestions == ["fortinet"]
    assert selected == "fortinet"
    assert "fortinet management API probe succeeded" in reasons


def test_classify_target_detects_cisco_from_snmp_sysdescr() -> None:
    target = discovery_service.PreparedTarget(host="10.0.0.19", source_kind="target")
    suggestions, selected, reasons = discovery_service._classify_target(
        target,
        {
            "open_ports": [],
            "ssh_banner": None,
            "http": [],
            "redis": None,
            "postgres": None,
            "ldap": None,
            "snmp_probe": {"status": "detected", "sys_descr": "Cisco IOS XE Software"},
            "management_apis": {},
        },
    )

    assert suggestions == ["cisco"]
    assert selected == "cisco"
    assert "SNMP sysDescr matched cisco" in reasons


@pytest.mark.asyncio
async def test_probe_target_marks_snmp_only_target_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_tcp_probe(host, port, timeout_seconds):
        return {"port": port, "open": False, "error": "timed out"}

    async def fake_probe_http(host, port, timeout_seconds):
        return None

    monkeypatch.setattr(discovery_service, "_tcp_probe", fake_tcp_probe)
    monkeypatch.setattr(discovery_service, "_probe_http", fake_probe_http)
    monkeypatch.setattr(discovery_service, "_probe_redis", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery_service, "_probe_postgres", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery_service, "_probe_ldap", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery_service, "_probe_vendor_management_apis", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        discovery_service,
        "_probe_snmp",
        lambda host, port, timeout_seconds: {"status": "detected", "sys_descr": "Cisco IOS XE Software"},
    )

    target = discovery_service.PreparedTarget(host="10.0.0.20", source_kind="target")
    result = await discovery_service._probe_target(target, [161], 3)

    assert result["status"] == "reachable"
    assert result["facts"]["evidence"]["reachable"] is True
    assert result["facts"]["evidence"]["snmp_identified"] is True
    assert result["selected_connector_type"] == "cisco"


@pytest.mark.asyncio
async def test_bootstrap_discovery_session_creates_and_syncs_connector(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register_admin(client, email="discovery-bootstrap-admin@deplyx.io")

    async def fake_probe_targets(targets, ports, timeout_seconds):
        return [
            {
                "host": "192.168.1.10",
                "name_hint": "sw-core-01",
                "source_kind": "inventory",
                "status": "reachable",
                "selected_connector_type": "cisco",
                "suggested_connector_types": ["cisco"],
                "probe_detail": {"ports": [{"port": 22, "open": True, "error": None}]},
                "facts": {"open_ports": [22], "ssh_banner": "SSH-2.0-OpenSSH_9.0", "http": [], "snmp_probe": {"status": "not_implemented"}},
                "classification_reasons": ["inventory declared connector_type=cisco"],
                "error": None,
            }
        ]

    async def fake_preflight(connector_type, config, facts):
        assert connector_type == "cisco"
        assert config["host"] == "192.168.1.10"
        assert config["username"] == "admin"
        return {"status": "passed", "message": "SSH authentication succeeded"}

    monkeypatch.setattr(discovery_service, "_probe_targets", fake_probe_targets)
    monkeypatch.setattr(discovery_service, "_preflight_connector", fake_preflight)

    created = await client.post(
        "/api/v1/discovery/sessions",
        json={
            "inventory": [{"host": "192.168.1.10", "name": "sw-core-01", "connector_type": "cisco"}],
        },
        headers=headers,
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    from app.services import connector_service

    class FakeConnector:
        def __init__(self, config: dict):
            self.config = config

        async def sync(self) -> dict:
            return {"vendor": "fake", "status": "synced", "synced": {"devices": 1}}

        async def validate_change(self, payload: dict) -> dict:
            return {"valid": True}

        async def simulate_change(self, payload: dict) -> dict:
            return {"simulation": "ok"}

        async def apply_change(self, payload: dict) -> dict:
            return {"applied": True}

    monkeypatch.setitem(connector_service.CONNECTOR_CLASSES, "cisco", FakeConnector)

    bootstrap = await client.post(
        f"/api/v1/discovery/sessions/{session_id}/bootstrap",
        json={
            "connector_defaults": {"cisco": {"username": "admin", "password": "Cisco123!", "driver_type": "ios"}},
            "run_sync": True,
        },
        headers=headers,
    )
    assert bootstrap.status_code == 200
    body = bootstrap.json()
    assert body["created"] == 0
    assert body["synced"] == 1
    assert body["errors"] == 0
    assert body["items"][0]["bootstrap_status"] == "synced"
    assert body["items"][0]["connector_name"] == "sw-core-01 (cisco)"

    connectors = await client.get("/api/v1/connectors", headers=headers)
    assert connectors.status_code == 200
    assert any(item["config"]["host"] == "192.168.1.10" for item in connectors.json())


@pytest.mark.asyncio
async def test_bootstrap_discovery_session_skips_ambiguous_result(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register_admin(client, email="discovery-bootstrap-ambiguous@deplyx.io")

    async def fake_probe_targets(targets, ports, timeout_seconds):
        return [
            {
                "host": "192.168.1.20",
                "name_hint": None,
                "source_kind": "target",
                "status": "reachable",
                "selected_connector_type": None,
                "suggested_connector_types": ["cisco", "juniper"],
                "probe_detail": {"ports": [{"port": 22, "open": True, "error": None}]},
                "facts": {"open_ports": [22], "ssh_banner": "SSH-2.0-OpenSSH_9.0", "http": [], "snmp_probe": {"status": "not_implemented"}},
                "classification_reasons": ["SSH is reachable but no vendor-specific fingerprint matched"],
                "error": None,
            }
        ]

    monkeypatch.setattr(discovery_service, "_probe_targets", fake_probe_targets)

    created = await client.post(
        "/api/v1/discovery/sessions",
        json={"targets": ["192.168.1.20"]},
        headers=headers,
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    bootstrap = await client.post(
        f"/api/v1/discovery/sessions/{session_id}/bootstrap",
        json={"connector_defaults": {"cisco": {"username": "admin", "password": "Cisco123!"}}},
        headers=headers,
    )
    assert bootstrap.status_code == 200
    body = bootstrap.json()
    assert body["skipped"] == 1
    assert body["items"][0]["bootstrap_status"] == "skipped_ambiguous"


@pytest.mark.asyncio
async def test_bootstrap_discovery_session_supports_result_override_selection(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register_admin(client, email="discovery-bootstrap-override@deplyx.io")

    async def fake_probe_targets(targets, ports, timeout_seconds):
        return [
            {
                "host": "192.168.1.30",
                "name_hint": None,
                "source_kind": "target",
                "status": "reachable",
                "selected_connector_type": None,
                "suggested_connector_types": ["cisco", "juniper"],
                "probe_detail": {"ports": [{"port": 22, "open": True, "error": None}]},
                "facts": {
                    "open_ports": [22],
                    "ssh_banner": "SSH-2.0-OpenSSH_9.0",
                    "http": [],
                    "snmp_probe": {"status": "not_implemented"},
                },
                "classification_reasons": ["SSH is reachable but no vendor-specific fingerprint matched"],
                "error": None,
            },
            {
                "host": "192.168.1.31",
                "name_hint": None,
                "source_kind": "target",
                "status": "reachable",
                "selected_connector_type": "juniper",
                "suggested_connector_types": ["juniper"],
                "probe_detail": {"ports": [{"port": 22, "open": True, "error": None}]},
                "facts": {
                    "open_ports": [22],
                    "ssh_banner": "SSH-2.0-OpenSSH_9.0",
                    "http": [],
                    "snmp_probe": {"status": "not_implemented"},
                },
                "classification_reasons": ["name or metadata tokens matched juniper"],
                "error": None,
            },
        ]

    async def fake_preflight(connector_type, config, facts):
        return {"status": "passed", "message": f"{connector_type} preflight passed"}

    monkeypatch.setattr(discovery_service, "_probe_targets", fake_probe_targets)
    monkeypatch.setattr(discovery_service, "_preflight_connector", fake_preflight)

    created = await client.post(
        "/api/v1/discovery/sessions",
        json={"targets": ["192.168.1.30", "192.168.1.31"]},
        headers=headers,
    )
    assert created.status_code == 201
    session = created.json()
    session_id = session["id"]
    ambiguous_result_id = session["results"][0]["id"]

    from app.services import connector_service

    class FakeConnector:
        def __init__(self, config: dict):
            self.config = config

        async def sync(self) -> dict:
            return {"vendor": "fake", "status": "synced", "synced": {"devices": 1}}

        async def validate_change(self, payload: dict) -> dict:
            return {"valid": True}

        async def simulate_change(self, payload: dict) -> dict:
            return {"simulation": "ok"}

        async def apply_change(self, payload: dict) -> dict:
            return {"applied": True}

    monkeypatch.setitem(connector_service.CONNECTOR_CLASSES, "cisco", FakeConnector)

    bootstrap = await client.post(
        f"/api/v1/discovery/sessions/{session_id}/bootstrap",
        json={
            "connector_defaults": {"cisco": {"username": "admin", "password": "Cisco123!"}},
            "items": [{"result_id": ambiguous_result_id, "connector_type": "cisco", "run_sync": False}],
            "run_sync": True,
        },
        headers=headers,
    )
    assert bootstrap.status_code == 200
    body = bootstrap.json()
    assert body["processed"] == 1
    assert body["created"] == 1
    assert body["synced"] == 0
    assert body["items"][0]["connector_type"] == "cisco"
    assert body["items"][0]["bootstrap_status"] == "created"
    assert body["items"][0]["detail"]["connector_type_override"] == "cisco"