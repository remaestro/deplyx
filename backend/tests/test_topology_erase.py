from datetime import datetime, timedelta, UTC

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api import graph as graph_api
from app.models.change import Change
from app.models.connector import Connector


async def _register_admin(client: AsyncClient, email: str = "topology-erase-admin@deplyx.io") -> dict[str, str]:
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
async def test_topology_erase_preserves_connectors_and_changes(client: AsyncClient, db, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = await _register_admin(client)

    async def _noop_clear_all() -> None:
        return None

    monkeypatch.setattr(graph_api.neo4j_client, "clear_all", _noop_clear_all)

    connector_res = await client.post(
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
    assert connector_res.status_code == 201

    now = datetime.now(UTC)
    change_res = await client.post(
        "/api/v1/changes",
        json={
            "title": "Erase topology regression",
            "change_type": "Preventive",
            "environment": "prod",
            "action": "config_change",
            "description": "Natural language description",
            "execution_plan": "execute",
            "rollback_plan": "rollback",
            "maintenance_window_start": now.isoformat(),
            "maintenance_window_end": (now + timedelta(hours=1)).isoformat(),
            "target_components": [],
        },
        headers=headers,
    )
    assert change_res.status_code == 201
    change_id = change_res.json()["id"]

    change = (await db.execute(select(Change).where(Change.id == change_id))).scalar_one()
    change.impact_cache = {"foo": "bar"}
    change.risk_score = 42.0
    change.risk_level = "medium"
    await db.commit()

    erase_res = await client.post("/api/v1/graph/topology/erase", headers=headers)
    assert erase_res.status_code == 200
    body = erase_res.json()
    assert body["status"] == "ok"
    assert "obsolete" in body["message"].lower() or "stale" in body["message"].lower()

    connectors = list((await db.execute(select(Connector))).scalars().all())
    assert len(connectors) == 1
    assert connectors[0].status == "inactive"
    assert connectors[0].last_sync_at is None
    assert connectors[0].last_error is None

    updated_change = (await db.execute(select(Change).where(Change.id == change_id))).scalar_one()
    await db.refresh(updated_change)
    assert updated_change is not None
    assert updated_change.impact_cache is None
    assert updated_change.risk_score is None
    assert updated_change.risk_level is None
