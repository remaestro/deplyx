import pytest

from app.api import changes as changes_api


class _Component:
    def __init__(self, graph_node_id: str, component_type: str, impact_level: str):
        self.graph_node_id = graph_node_id
        self.component_type = component_type
        self.impact_level = impact_level


class _Change:
    id = "c-1"
    title = "t"
    change_type = "Firewall"
    environment = "Prod"
    action = "add_rule"
    description = "d"
    execution_plan = "e"
    rollback_plan = "r"
    maintenance_window_start = None
    maintenance_window_end = None
    status = "Draft"
    risk_score = None
    risk_level = None
    analysis_stage = "pending"
    analysis_attempts = 0
    analysis_last_error = None
    analysis_trace_id = None
    created_by = 1
    reject_reason = None
    created_at = None
    updated_at = None
    impacted_components = [_Component("FW-1", "Device", "direct")]


@pytest.mark.asyncio
async def test_change_serializer_adds_display_name(monkeypatch: pytest.MonkeyPatch):
    async def _fake_run_query(_cypher, _params):
        return [{"node_label": "Device", "display_name": "Fortinet Firewall — fw-dc1-01", "node_name": None, "hostname": None}]

    monkeypatch.setattr(changes_api.neo4j_client, "run_query", _fake_run_query)

    payload = await changes_api._serialize_change(_Change())
    assert payload["impacted_components"][0]["display_name"] == "Fortinet Firewall — fw-dc1-01"
    assert payload["impacted_components"][0]["label"] == "Device"
