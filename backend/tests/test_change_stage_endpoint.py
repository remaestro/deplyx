import pytest

from app.services import change_service
from tests.test_changes import _register_admin


@pytest.mark.asyncio
async def test_get_change_stage_endpoint(client, monkeypatch: pytest.MonkeyPatch):
    async def _fake_impacted_components(target_components, depth=2, action=None):
        return [
            {
                "graph_node_id": target_components[0] if target_components else "FW-DC1-01",
                "component_type": "Device",
                "impact_level": "direct",
            }
        ]

    monkeypatch.setattr(change_service, "_build_impacted_components", _fake_impacted_components)

    headers = await _register_admin(client)
    created = await client.post(
        "/api/v1/changes",
        json={
            "title": "Stage endpoint",
            "change_type": "Firewall",
            "environment": "Prod",
            "description": "desc",
            "execution_plan": "exec",
            "rollback_plan": "rollback",
            "maintenance_window_start": "2030-01-01T00:00:00Z",
            "maintenance_window_end": "2030-01-01T01:00:00Z",
            "target_components": ["FW-DC1-01"],
            "action": "add_rule",
        },
        headers=headers,
    )
    cid = created.json()["id"]

    res = await client.get(f"/api/v1/changes/{cid}/stage", headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert payload["analysis_stage"] == "pending"
    assert payload["analysis_attempts"] == 0
