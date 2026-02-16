"""Tests for connector management and sync endpoints."""

import pytest
from httpx import AsyncClient

from app.services import connector_service


class FakeConnector:
    def __init__(self, config: dict):
        self.config = config

    async def sync(self) -> dict:
        return {"vendor": "fake", "status": "synced", "synced": {"devices": 1}}

    async def validate_change(self, payload: dict) -> dict:
        return {"vendor": "fake", "valid": True, "payload": payload}

    async def simulate_change(self, payload: dict) -> dict:
        return {"vendor": "fake", "simulation": "ok", "payload": payload}

    async def apply_change(self, payload: dict) -> dict:
        return {"vendor": "fake", "applied": True, "payload": payload}


async def _register_admin(client: AsyncClient, email: str = "connectors-admin@deplyx.io") -> dict[str, str]:
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
async def test_create_list_and_sync_connector(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = await _register_admin(client, email="sync-admin@deplyx.io")

    monkeypatch.setitem(connector_service.CONNECTOR_CLASSES, "paloalto", FakeConnector)

    created = await client.post(
        "/api/v1/connectors",
        json={
            "name": "PA Connector",
            "connector_type": "paloalto",
            "config": {"host": "demo.local"},
            "sync_mode": "on-demand",
            "sync_interval_minutes": 30,
        },
        headers=headers,
    )
    assert created.status_code == 201
    connector_id = created.json()["id"]

    listed = await client.get("/api/v1/connectors", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == connector_id for item in listed.json())

    synced = await client.post(f"/api/v1/connectors/{connector_id}/sync", headers=headers)
    assert synced.status_code == 200
    assert synced.json()["status"] == "synced"

    fetched = await client.get(f"/api/v1/connectors/{connector_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "active"
    assert fetched.json()["last_sync_at"] is not None


@pytest.mark.asyncio
async def test_webhook_sync_mode_guard(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = await _register_admin(client, email="webhook-guard-admin@deplyx.io")

    monkeypatch.setitem(connector_service.CONNECTOR_CLASSES, "paloalto", FakeConnector)

    created = await client.post(
        "/api/v1/connectors",
        json={
            "name": "Pull Connector",
            "connector_type": "paloalto",
            "config": {"host": "demo.local"},
            "sync_mode": "pull",
            "sync_interval_minutes": 60,
        },
        headers=headers,
    )
    connector_id = created.json()["id"]

    webhook = await client.post(
        f"/api/v1/connectors/{connector_id}/webhook",
        json={"event": "manual"},
        headers=headers,
    )
    assert webhook.status_code == 400
    assert "not configured for webhook" in webhook.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_sync_success(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = await _register_admin(client, email="webhook-success-admin@deplyx.io")

    monkeypatch.setitem(connector_service.CONNECTOR_CLASSES, "paloalto", FakeConnector)

    created = await client.post(
        "/api/v1/connectors",
        json={
            "name": "Webhook Connector",
            "connector_type": "paloalto",
            "config": {"host": "demo.local"},
            "sync_mode": "webhook",
            "sync_interval_minutes": 10,
        },
        headers=headers,
    )
    connector_id = created.json()["id"]

    webhook = await client.post(
        f"/api/v1/connectors/{connector_id}/webhook",
        json={"event": "manual"},
        headers=headers,
    )
    assert webhook.status_code == 200
    body = webhook.json()
    assert body["status"] == "synced"
    assert body["trigger"] == "webhook"
    assert body["received_payload"] is True


@pytest.mark.asyncio
async def test_pull_sync_endpoint(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = await _register_admin(client, email="pull-sync-admin@deplyx.io")

    monkeypatch.setitem(connector_service.CONNECTOR_CLASSES, "paloalto", FakeConnector)

    created = await client.post(
        "/api/v1/connectors",
        json={
            "name": "Pull Due Connector",
            "connector_type": "paloalto",
            "config": {"host": "demo.local"},
            "sync_mode": "pull",
            "sync_interval_minutes": 60,
        },
        headers=headers,
    )
    assert created.status_code == 201

    res = await client.post("/api/v1/connectors/sync/pull", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["considered"] >= 1
    assert body["synced"] >= 1


@pytest.mark.asyncio
async def test_validate_simulate_apply_endpoints(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = await _register_admin(client, email="orchestration-admin@deplyx.io")

    monkeypatch.setitem(connector_service.CONNECTOR_CLASSES, "paloalto", FakeConnector)

    created = await client.post(
        "/api/v1/connectors",
        json={
            "name": "Orchestration Connector",
            "connector_type": "paloalto",
            "config": {"host": "demo.local"},
            "sync_mode": "on-demand",
            "sync_interval_minutes": 30,
        },
        headers=headers,
    )
    connector_id = created.json()["id"]

    payload = {"rule_name": "allow-web", "rule_config": {"action": "allow"}}

    validate = await client.post(f"/api/v1/connectors/{connector_id}/validate", json=payload, headers=headers)
    assert validate.status_code == 200
    assert validate.json()["valid"] is True

    simulate = await client.post(f"/api/v1/connectors/{connector_id}/simulate", json=payload, headers=headers)
    assert simulate.status_code == 200
    assert simulate.json()["simulation"] == "ok"

    apply = await client.post(f"/api/v1/connectors/{connector_id}/apply", json=payload, headers=headers)
    assert apply.status_code == 200
    assert apply.json()["applied"] is True
