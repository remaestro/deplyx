"""Fake IGraphClient for unit tests.

Stores nodes and relationships in plain dicts so tests can inspect them
without a running Neo4j instance.
"""

from typing import Any


class FakeGraphClient:
    """In-memory graph client that satisfies the IGraphClient protocol."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.relationships: list[dict[str, Any]] = []
        self._closed = False

    async def merge_node(self, label: str, node_id: str, properties: dict[str, Any]) -> None:
        self.nodes[node_id] = {"label": label, "id": node_id, **properties}

    async def create_relationship(
        self,
        src_label: str,
        src_id: str,
        rel_type: str,
        dst_label: str,
        dst_id: str,
    ) -> None:
        self.relationships.append({
            "src_label": src_label,
            "src_id": src_id,
            "rel_type": rel_type,
            "dst_label": dst_label,
            "dst_id": dst_id,
        })

    async def get_full_topology(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes.values()),
            "relationships": self.relationships,
        }

    async def close(self) -> None:
        self._closed = True
