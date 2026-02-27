import pytest

from app.graph.neo4j_client import neo4j_client


@pytest.mark.asyncio
async def test_search_nodes_query_includes_display_name(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    async def _fake_run_query(cypher, params=None):
        captured["cypher"] = cypher
        return []

    monkeypatch.setattr(neo4j_client, "run_query", _fake_run_query)
    await neo4j_client.search_nodes("fw", limit=5)

    assert "coalesce(n.display_name" in captured["cypher"]
    assert "ORDER BY coalesce(n.display_name" in captured["cypher"]
