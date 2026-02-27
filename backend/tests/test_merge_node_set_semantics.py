import pytest

from app.graph.neo4j_client import neo4j_client


@pytest.mark.asyncio
async def test_merge_node_uses_property_merge(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    async def _fake_run_write(cypher, params=None):
        captured["cypher"] = cypher
        captured["params"] = params
        return [{"n": {"id": "X"}}]

    monkeypatch.setattr(neo4j_client, "run_write", _fake_run_write)

    await neo4j_client.merge_node("Device", "X", {"display_name": "Device X"})

    assert "MERGE (n:Device {id: $id})" in captured["cypher"]
    assert "SET n += $props" in captured["cypher"]
