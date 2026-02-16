from typing import Any

from neo4j import AsyncGraphDatabase

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class Neo4jClient:
    def __init__(self) -> None:
        self.driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )

    async def close(self) -> None:
        await self.driver.close()

    # ── Generic helpers ────────────────────────────────────────────────

    async def run_query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        async with self.driver.session() as session:
            result = await session.run(cypher, params or {})
            return [record.data() async for record in result]

    async def run_write(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        async with self.driver.session() as session:
            result = await session.run(cypher, params or {})
            return [record.data() async for record in result]

    # ── Node CRUD ──────────────────────────────────────────────────────

    async def create_node(self, label: str, props: dict[str, Any]) -> dict[str, Any]:
        cypher = f"CREATE (n:{label} $props) RETURN n"
        rows = await self.run_write(cypher, {"props": props})
        return rows[0]["n"] if rows else {}

    async def merge_node(self, label: str, id_value: str, props: dict[str, Any]) -> dict[str, Any]:
        cypher = f"MERGE (n:{label} {{id: $id}}) SET n += $props RETURN n"
        rows = await self.run_write(cypher, {"id": id_value, "props": props})
        return rows[0]["n"] if rows else {}

    async def get_node(self, label: str, id_value: str) -> dict[str, Any] | None:
        cypher = f"MATCH (n:{label} {{id: $id}}) RETURN n"
        rows = await self.run_query(cypher, {"id": id_value})
        return rows[0]["n"] if rows else None

    async def get_all_nodes(self, label: str) -> list[dict[str, Any]]:
        cypher = f"MATCH (n:{label}) RETURN n ORDER BY n.id"
        rows = await self.run_query(cypher)
        return [r["n"] for r in rows]

    async def update_node(self, label: str, id_value: str, props: dict[str, Any]) -> dict[str, Any] | None:
        cypher = f"MATCH (n:{label} {{id: $id}}) SET n += $props RETURN n"
        rows = await self.run_write(cypher, {"id": id_value, "props": props})
        return rows[0]["n"] if rows else None

    async def delete_node(self, label: str, id_value: str) -> bool:
        cypher = f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n RETURN count(n) as deleted"
        rows = await self.run_write(cypher, {"id": id_value})
        return rows[0]["deleted"] > 0 if rows else False

    # ── Relationship CRUD ──────────────────────────────────────────────

    async def create_relationship(
        self,
        from_label: str,
        from_id: str,
        rel_type: str,
        to_label: str,
        to_id: str,
        props: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cypher = (
            f"MATCH (a:{from_label} {{id: $from_id}}), (b:{to_label} {{id: $to_id}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            "SET r += $props "
            "RETURN type(r) as rel_type, a.id as from_id, b.id as to_id"
        )
        rows = await self.run_write(cypher, {"from_id": from_id, "to_id": to_id, "props": props or {}})
        return rows[0] if rows else {}

    # ── Graph traversal ────────────────────────────────────────────────

    async def get_neighbors(
        self,
        node_id: str,
        rel_types: list[str] | None = None,
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        rel_filter = "|".join(rel_types) if rel_types else ""
        rel_pattern = f"[:{rel_filter}*1..{depth}]" if rel_filter else f"[*1..{depth}]"
        cypher = (
            f"MATCH (start {{id: $id}})-{rel_pattern}-(neighbor) "
            "RETURN DISTINCT neighbor.id as id, labels(neighbor)[0] as label, properties(neighbor) as props"
        )
        return await self.run_query(cypher, {"id": node_id})

    async def get_impact_subgraph(self, node_id: str, depth: int = 3) -> dict[str, Any]:
        """Return nodes and edges reachable from node_id within depth hops."""
        cypher = """
        MATCH path = (start {id: $id})-[*1..%(depth)s]-(end)
        WITH nodes(path) as ns, relationships(path) as rs
        UNWIND ns as n
        WITH COLLECT(DISTINCT {id: n.id, label: labels(n)[0], properties: properties(n)}) as nodes,
             rs
        UNWIND rs as r
        WITH nodes,
             COLLECT(DISTINCT {
                source: startNode(r).id,
                target: endNode(r).id,
                rel_type: type(r),
                properties: properties(r)
             }) as edges
        RETURN nodes, edges
        """ % {"depth": depth}
        rows = await self.run_query(cypher, {"id": node_id})
        if rows:
            return {"nodes": rows[0]["nodes"], "edges": rows[0]["edges"]}
        return {"nodes": [], "edges": []}

    async def get_impact_subgraph_multi(self, node_ids: list[str], depth: int = 3) -> dict[str, Any]:
        """Return the merged subgraph reachable within *depth* hops from any of
        the supplied *node_ids*.  Much smaller than the full topology, which
        makes the LLM prompt faster and cheaper."""
        if not node_ids:
            return {"nodes": [], "edges": []}
        cypher = """
        UNWIND $ids AS target_id
        MATCH path = (start {id: target_id})-[*1..%(depth)s]-(end)
        WITH nodes(path) AS ns, relationships(path) AS rs
        UNWIND ns AS n
        WITH COLLECT(DISTINCT n) AS all_nodes, COLLECT(DISTINCT rs) AS all_rs_list
        UNWIND all_rs_list AS rs_inner
        UNWIND rs_inner AS r
        WITH all_nodes, COLLECT(DISTINCT r) AS all_rels
        UNWIND all_nodes AS n
        WITH COLLECT(DISTINCT {
                id: n.id,
                label: labels(n)[0],
                properties: properties(n)
             }) AS nodes,
             all_rels
        UNWIND all_rels AS r
        RETURN nodes,
               COLLECT(DISTINCT {
                  source: startNode(r).id,
                  target: endNode(r).id,
                  rel_type: type(r),
                  properties: properties(r)
               }) AS edges
        """ % {"depth": depth}
        rows = await self.run_query(cypher, {"ids": node_ids})
        if rows:
            return {"nodes": rows[0]["nodes"], "edges": rows[0]["edges"]}
        return {"nodes": [], "edges": []}

    # ── Full topology ──────────────────────────────────────────────────

    async def get_full_topology(self) -> dict[str, Any]:
        nodes_cypher = "MATCH (n) RETURN n.id as id, labels(n)[0] as label, properties(n) as properties"
        edges_cypher = (
            "MATCH (a)-[r]->(b) "
            "RETURN a.id as source, b.id as target, type(r) as rel_type, properties(r) as properties, "
            "a.id + '-' + type(r) + '-' + b.id as id"
        )
        nodes = await self.run_query(nodes_cypher)
        edges = await self.run_query(edges_cypher)
        return {"nodes": nodes, "edges": edges}

    # ── Action-aware impact queries ────────────────────────────────────

    async def get_rule_dependents(self, rule_id: str) -> list[dict[str, Any]]:
        """Find apps/services that depend on a specific firewall rule via PROTECTS."""
        cypher = """
        MATCH (r:Rule {id: $id})-[:PROTECTS]->(app)
        RETURN DISTINCT app.id as id, labels(app)[0] as label, properties(app) as props
        UNION
        MATCH (r:Rule {id: $id})<-[:HAS_RULE]-(fw:Device)-[:CONNECTED_TO*1..2]-(neighbor)
        RETURN DISTINCT neighbor.id as id, labels(neighbor)[0] as label, properties(neighbor) as props
        """
        return await self.run_query(cypher, {"id": rule_id})

    async def get_port_dependents(self, node_id: str) -> list[dict[str, Any]]:
        """Find what depends on a port/interface — follow cables, VLANs, connected devices."""
        cypher = """
        MATCH (p {id: $id})-[:PART_OF|CONNECTED_TO|HAS_INTERFACE*1..2]-(neighbor)
        RETURN DISTINCT neighbor.id as id, labels(neighbor)[0] as label, properties(neighbor) as props
        UNION
        MATCH (p {id: $id})-[:PART_OF]->(:Device)-[:HAS_INTERFACE]->(:Interface)-[:PART_OF]->(v:VLAN)
        WITH v
        MATCH (v)<-[:PART_OF]-(:Interface)<-[:HAS_INTERFACE]-(dev:Device)
        RETURN DISTINCT dev.id as id, labels(dev)[0] as label, properties(dev) as props
        """
        return await self.run_query(cypher, {"id": node_id})

    async def get_vlan_members(self, vlan_id: str) -> list[dict[str, Any]]:
        """Find all devices and interfaces on a VLAN."""
        cypher = """
        MATCH (v:VLAN {id: $id})<-[:PART_OF]-(iface:Interface)<-[:HAS_INTERFACE]-(dev:Device)
        RETURN DISTINCT dev.id as id, labels(dev)[0] as label, properties(dev) as props
        UNION
        MATCH (v:VLAN {id: $id})<-[:PART_OF]-(iface:Interface)
        RETURN DISTINCT iface.id as id, labels(iface)[0] as label, properties(iface) as props
        """
        return await self.run_query(cypher, {"id": vlan_id})

    async def get_device_full_impact(self, device_id: str) -> list[dict[str, Any]]:
        """For device-level actions (reboot, decommission): everything connected."""
        cypher = """
        MATCH (d:Device {id: $id})-[:CONNECTED_TO|HAS_INTERFACE|HAS_RULE|HOSTS*1..3]-(neighbor)
        RETURN DISTINCT neighbor.id as id, labels(neighbor)[0] as label, properties(neighbor) as props
        UNION
        MATCH (d:Device {id: $id})-[:HAS_RULE]->(r:Rule)-[:PROTECTS]->(app)
        RETURN DISTINCT app.id as id, labels(app)[0] as label, properties(app) as props
        UNION
        MATCH (d:Device {id: $id})-[:CONNECTED_TO*1..2]-(peer:Device)-[:HOSTS]->(svc)
        RETURN DISTINCT svc.id as id, labels(svc)[0] as label, properties(svc) as props
        """
        return await self.run_query(cypher, {"id": device_id})

    # ── Action-aware dispatch ──────────────────────────────────────────

    _RULE_ACTIONS = {"add_rule", "remove_rule", "modify_rule", "disable_rule"}
    _PORT_ACTIONS = {"disable_port", "enable_port", "shutdown_interface"}
    _VLAN_ACTIONS = {"change_vlan", "delete_vlan", "modify_vlan"}
    _DEVICE_ACTIONS = {"reboot_device", "decommission", "firmware_upgrade", "delete_sg"}

    async def get_action_aware_neighbors(
        self, node_id: str, action: str | None = None, depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Dispatch to the appropriate neighbor query based on change action."""
        if not action:
            return await self.get_neighbors(node_id, depth=depth)
        a = action.lower()
        if a in self._RULE_ACTIONS:
            return await self.get_rule_dependents(node_id)
        if a in self._PORT_ACTIONS:
            return await self.get_port_dependents(node_id)
        if a in self._VLAN_ACTIONS:
            return await self.get_vlan_members(node_id)
        if a in self._DEVICE_ACTIONS:
            return await self.get_device_full_impact(node_id)
        return await self.get_neighbors(node_id, depth=min(depth, 2))

    # ── Critical-path queries ──────────────────────────────────────────

    async def get_critical_paths(
        self, node_id: str, action: str | None = None, depth: int = 3,
    ) -> list[dict[str, Any]]:
        """Return dependency *paths* (not just endpoints) based on change action."""
        if not action:
            return await self._generic_paths(node_id, depth)
        a = action.lower()
        if a in self._RULE_ACTIONS:
            return await self._rule_paths(node_id)
        if a in self._PORT_ACTIONS:
            return await self._port_paths(node_id)
        if a in self._VLAN_ACTIONS:
            return await self._vlan_paths(node_id)
        if a in self._DEVICE_ACTIONS:
            return await self._device_paths(node_id)
        return await self._generic_paths(node_id, min(depth, 2))

    async def _rule_paths(self, rule_id: str) -> list[dict[str, Any]]:
        cypher = """
        MATCH path = (start {id: $id})-[:PROTECTS]->(app)
        RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], props: properties(n)}] AS path_nodes,
               [rel IN relationships(path) | {type: type(rel), source: startNode(rel).id, target: endNode(rel).id}] AS path_edges
        UNION ALL
        MATCH path = (start {id: $id})<-[:HAS_RULE]-(fw)-[:CONNECTED_TO*1..2]-(neighbor)
        WHERE neighbor <> start
        RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], props: properties(n)}] AS path_nodes,
               [rel IN relationships(path) | {type: type(rel), source: startNode(rel).id, target: endNode(rel).id}] AS path_edges
        """
        return await self.run_query(cypher, {"id": rule_id})

    async def _port_paths(self, node_id: str) -> list[dict[str, Any]]:
        cypher = """
        MATCH path = (start {id: $id})-[:PART_OF|CONNECTED_TO|HAS_INTERFACE*1..2]-(neighbor)
        WHERE neighbor <> start
        RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], props: properties(n)}] AS path_nodes,
               [rel IN relationships(path) | {type: type(rel), source: startNode(rel).id, target: endNode(rel).id}] AS path_edges
        """
        return await self.run_query(cypher, {"id": node_id})

    async def _vlan_paths(self, vlan_id: str) -> list[dict[str, Any]]:
        cypher = """
        MATCH path = (v:VLAN {id: $id})<-[:PART_OF]-(iface:Interface)<-[:HAS_INTERFACE]-(dev:Device)
        RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], props: properties(n)}] AS path_nodes,
               [rel IN relationships(path) | {type: type(rel), source: startNode(rel).id, target: endNode(rel).id}] AS path_edges
        UNION ALL
        MATCH path = (v:VLAN {id: $id})-[:ROUTES_TO]->(app:Application)
        RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], props: properties(n)}] AS path_nodes,
               [rel IN relationships(path) | {type: type(rel), source: startNode(rel).id, target: endNode(rel).id}] AS path_edges
        """
        return await self.run_query(cypher, {"id": vlan_id})

    async def _device_paths(self, device_id: str) -> list[dict[str, Any]]:
        cypher = """
        MATCH path = (d:Device {id: $id})-[:HAS_RULE]->(rule:Rule)-[:PROTECTS]->(app:Application)
        RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], props: properties(n)}] AS path_nodes,
               [rel IN relationships(path) | {type: type(rel), source: startNode(rel).id, target: endNode(rel).id}] AS path_edges
        UNION ALL
        MATCH path = (d:Device {id: $id})-[:CONNECTED_TO*1..3]-(peer:Device)
        WHERE d <> peer
        RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], props: properties(n)}] AS path_nodes,
               [rel IN relationships(path) | {type: type(rel), source: startNode(rel).id, target: endNode(rel).id}] AS path_edges
        UNION ALL
        MATCH path = (d:Device {id: $id})-[:HOSTS]->(v:VLAN)-[:ROUTES_TO]->(app:Application)
        RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], props: properties(n)}] AS path_nodes,
               [rel IN relationships(path) | {type: type(rel), source: startNode(rel).id, target: endNode(rel).id}] AS path_edges
        """
        return await self.run_query(cypher, {"id": device_id})

    async def _generic_paths(self, node_id: str, depth: int) -> list[dict[str, Any]]:
        cypher = """
        MATCH path = (start {id: $id})-[*1..%(depth)s]-(endpoint)
        WHERE start <> endpoint
        WITH path
        ORDER BY length(path)
        LIMIT 30
        RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], props: properties(n)}] AS path_nodes,
               [rel IN relationships(path) | {type: type(rel), source: startNode(rel).id, target: endNode(rel).id}] AS path_edges
        """ % {"depth": depth}
        return await self.run_query(cypher, {"id": node_id})

    async def search_nodes(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search nodes by id or label substring for the node picker."""
        cypher = """
        MATCH (n)
        WHERE toLower(n.id) CONTAINS toLower($q)
           OR toLower(coalesce(n.label, '')) CONTAINS toLower($q)
           OR toLower(coalesce(n.hostname, '')) CONTAINS toLower($q)
           OR toLower(coalesce(n.name, '')) CONTAINS toLower($q)
        RETURN n.id as id, labels(n)[0] as label, properties(n) as props
        ORDER BY n.id
        LIMIT $limit
        """
        return await self.run_query(cypher, {"q": query, "limit": limit})

    # ── Clear all data ─────────────────────────────────────────────────

    async def clear_all(self) -> None:
        await self.run_write("MATCH (n) DETACH DELETE n")


neo4j_client = Neo4jClient()
