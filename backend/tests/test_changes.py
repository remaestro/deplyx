"""Tests for change management endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import make_token


async def _register_admin(client: AsyncClient) -> dict[str, str]:
    """Register an admin user and return auth headers."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "admin@deplyx.io", "password": "Admin123!", "role": "admin"},
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@deplyx.io", "password": "Admin123!"},
    )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_change(client: AsyncClient) -> None:
    headers = await _register_admin(client)
    res = await client.post(
        "/api/v1/changes",
        json={
            "title": "Add firewall rule",
            "change_type": "Firewall",
            "environment": "Prod",
            "description": "Add allow rule for web traffic",
            "execution_plan": "Apply firewall config",
            "rollback_plan": "Revert firewall config",
            "maintenance_window_start": "2030-01-01T00:00:00Z",
            "maintenance_window_end": "2030-01-01T01:00:00Z",
            "target_components": ["FW-DC1-01"],
        },
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Add firewall rule"
    assert data["status"] == "Draft"


@pytest.mark.asyncio
async def test_list_changes(client: AsyncClient) -> None:
    headers = await _register_admin(client)
    # Create two changes
    await client.post(
        "/api/v1/changes",
        json={
            "title": "Change 1",
            "change_type": "VLAN",
            "environment": "Preprod",
            "description": "Move VLAN",
            "execution_plan": "Apply VLAN update",
            "rollback_plan": "Revert VLAN update",
            "maintenance_window_start": "2030-01-01T00:00:00Z",
            "maintenance_window_end": "2030-01-01T01:00:00Z",
            "target_components": ["SW-DC1-CORE"],
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/changes",
        json={
            "title": "Change 2",
            "change_type": "Firewall",
            "environment": "Prod",
            "description": "Update firewall ACL",
            "execution_plan": "Apply ACL",
            "rollback_plan": "Revert ACL",
            "maintenance_window_start": "2030-01-01T02:00:00Z",
            "maintenance_window_end": "2030-01-01T03:00:00Z",
            "target_components": ["FW-DC1-01"],
        },
        headers=headers,
    )
    res = await client.get("/api/v1/changes", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 2


@pytest.mark.asyncio
async def test_submit_change(client: AsyncClient) -> None:
    headers = await _register_admin(client)
    res = await client.post(
        "/api/v1/changes",
        json={
            "title": "Submit test",
            "change_type": "Firewall",
            "environment": "Prod",
            "description": "Submit flow test",
            "execution_plan": "Apply firewall rule",
            "rollback_plan": "Revert firewall rule",
            "maintenance_window_start": "2030-01-01T00:00:00Z",
            "maintenance_window_end": "2030-01-01T01:00:00Z",
            "target_components": ["FW-DC1-01"],
        },
        headers=headers,
    )
    cid = res.json()["id"]

    res = await client.post(f"/api/v1/changes/{cid}/submit", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] in ("Pending", "Approved")


@pytest.mark.asyncio
async def test_delete_draft_change(client: AsyncClient) -> None:
    headers = await _register_admin(client)
    res = await client.post(
        "/api/v1/changes",
        json={
            "title": "To delete",
            "change_type": "Switch",
            "environment": "DC1",
            "description": "Delete test",
            "execution_plan": "Apply switch config",
            "rollback_plan": "Revert switch config",
            "maintenance_window_start": "2030-01-01T00:00:00Z",
            "maintenance_window_end": "2030-01-01T01:00:00Z",
            "target_components": ["SW-DC1-CORE"],
        },
        headers=headers,
    )
    cid = res.json()["id"]
    res = await client.delete(f"/api/v1/changes/{cid}", headers=headers)
    assert res.status_code == 204
