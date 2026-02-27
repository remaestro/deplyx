"""Action-aware impact analysis service.

Uses Google Gemini Flash LLM to reason about the full graph topology and
identify critical dependency paths, blast radius, and risk factors.
Falls back to rule-based Neo4j traversal when the LLM is unavailable.
"""

from typing import Any

import asyncio
import time

from app.graph.neo4j_client import neo4j_client
from app.services import llm_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# In-flight deduplication: key → asyncio.Future
# Prevents duplicate parallel LLM calls for the same change
_inflight: dict[str, asyncio.Future] = {}


async def analyze_impact(
    target_node_ids: list[str],
    action: str | None = None,
    depth: int = 3,
    change_type: str | None = None,
    environment: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Run impact analysis — LLM-powered when Gemini is available, otherwise
    falls back to rule-based Neo4j traversal."""

    # ── 1. Always run the graph traversal (provides structured data) ───
    t0 = time.monotonic()
    graph_result = await _graph_based_analysis(target_node_ids, action, depth)
    t_graph = time.monotonic() - t0
    logger.info("[IMPACT-DIAG] Graph analysis: %.1fs, %d direct + %d indirect nodes",
                t_graph, len(graph_result.get('directly_impacted', [])),
                len(graph_result.get('indirectly_impacted', [])))

    # ── 2. Try LLM analysis on top ──────────────────────────────────────
    llm_result = None
    if llm_service.is_available():
        # Build a dedup key from the inputs that affect the LLM result
        dedup_key = f"{','.join(sorted(target_node_ids))}|{action}|{change_type}|{environment}"

        # Check if an identical LLM call is already in-flight
        if dedup_key in _inflight:
            logger.info("[IMPACT-DIAG] IN-FLIGHT HIT — waiting for existing LLM call (key=%s)", dedup_key)
            try:
                llm_result = await _inflight[dedup_key]
                logger.info("[IMPACT-DIAG] IN-FLIGHT resolved: result=%s", 'OK' if llm_result else 'NONE')
            except Exception as e:
                logger.warning("[IMPACT-DIAG] IN-FLIGHT wait failed: %s", e)
        else:
            # We are the first — create a future and run the LLM call
            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()
            _inflight[dedup_key] = future
            try:
                t_topo = time.monotonic()
                topology = await neo4j_client.get_impact_subgraph_multi(
                    target_node_ids, depth=4
                )
                t_topo_done = time.monotonic() - t_topo
                logger.info("[IMPACT-DIAG] Subgraph fetch: %.1fs (%d nodes, %d edges) — pruned to 4-hop neighborhood",
                            t_topo_done, len(topology.get('nodes', [])), len(topology.get('edges', [])))

                change_details = {
                    "action": action or "unknown",
                    "change_type": change_type or "unknown",
                    "environment": environment or "unknown",
                    "title": title or "",
                    "target_node_ids": target_node_ids,
                }
                t_llm = time.monotonic()
                llm_result = await llm_service.analyze_with_llm(topology, change_details)
                t_llm_done = time.monotonic() - t_llm
                logger.info("[IMPACT-DIAG] LLM call: %.1fs, result=%s",
                            t_llm_done, 'OK' if llm_result else 'NONE/FALLBACK')
                future.set_result(llm_result)
            except Exception as e:
                logger.error("[IMPACT-DIAG] LLM analysis EXCEPTION: %s", e)
                future.set_exception(e)
            finally:
                _inflight.pop(dedup_key, None)
    else:
        logger.info("[IMPACT-DIAG] LLM not available, using graph-only")

    # ── 3. Prefer LLM response shape when available ───────────────────
    if llm_result:
        result = _build_llm_first_response(
            target_node_ids=target_node_ids,
            action=action,
            graph_result=graph_result,
            llm_result=llm_result,
        )
    else:
        graph_result["llm_powered"] = False
        result = graph_result

    t_total = time.monotonic() - t0
    logger.info("[IMPACT-DIAG] TOTAL: %.1fs, llm_powered=%s", t_total, result["llm_powered"])

    return result


def _build_llm_first_response(
    *,
    target_node_ids: list[str],
    action: str | None,
    graph_result: dict[str, Any],
    llm_result: dict[str, Any],
) -> dict[str, Any]:
    critical_paths = llm_result.get("critical_paths") or []
    risk_assessment = llm_result.get("risk_assessment") or {}
    blast_radius = llm_result.get("blast_radius") or {}
    action_analysis = llm_result.get("action_analysis") or {}

    direct_map = {
        item.get("id"): item
        for item in (graph_result.get("directly_impacted") or [])
        if isinstance(item, dict) and item.get("id")
    }
    directly_impacted = [direct_map[node_id] for node_id in target_node_ids if node_id in direct_map]

    indirect_map: dict[str, dict[str, Any]] = {}
    for cp in critical_paths:
        if not isinstance(cp, dict):
            continue
        for node in cp.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            if not node_id or node_id in target_node_ids:
                continue
            if node_id not in indirect_map:
                indirect_map[node_id] = {
                    "id": node_id,
                    "label": node.get("label") or "",
                    "properties": {},
                }

    indirectly_impacted = list(indirect_map.values())
    affected_applications = [item for item in indirectly_impacted if item.get("label") == "Application"]
    affected_services = [item for item in indirectly_impacted if item.get("label") == "Service"]
    affected_vlans = [item for item in indirectly_impacted if item.get("label") == "VLAN"]

    total_dependency_count = blast_radius.get("total_impacted")
    if not isinstance(total_dependency_count, int):
        total_dependency_count = len(directly_impacted) + len(indirectly_impacted)

    max_criticality = risk_assessment.get("severity")
    if not isinstance(max_criticality, str):
        max_criticality = _compute_max_criticality(directly_impacted + indirectly_impacted)

    return {
        "directly_impacted": directly_impacted,
        "indirectly_impacted": indirectly_impacted,
        "affected_applications": affected_applications,
        "affected_services": affected_services,
        "affected_vlans": affected_vlans,
        "total_dependency_count": total_dependency_count,
        "max_criticality": max_criticality,
        "traversal_strategy": action_analysis.get("traversal_strategy") or _strategy_name(action),
        "critical_paths": critical_paths,
        "risk_assessment": risk_assessment,
        "blast_radius": blast_radius,
        "action_analysis": action_analysis,
        "llm_powered": True,
    }


async def _graph_based_analysis(
    target_node_ids: list[str],
    action: str | None,
    depth: int,
) -> dict[str, Any]:
    """Original rule-based graph traversal analysis."""

    directly_impacted: list[dict[str, Any]] = []
    indirectly_impacted: list[dict[str, Any]] = []
    affected_applications: list[dict[str, Any]] = []
    affected_services: list[dict[str, Any]] = []
    affected_vlans: list[dict[str, Any]] = []
    seen_ids: set[str] = set(target_node_ids)

    for node_id in target_node_ids:
        node = None
        for label in ["Device", "Rule", "VLAN", "Application", "Interface", "Service", "IP", "Port"]:
            node = await neo4j_client.get_node(label, node_id)
            if node:
                directly_impacted.append({"id": node_id, "label": label, "properties": node})
                break

        logger.info("Action-aware traversal for %s (action=%s, depth=%d)", node_id, action, depth)
        neighbors = await neo4j_client.get_action_aware_neighbors(node_id, action=action, depth=depth)

        for n in neighbors:
            nid = n.get("id")
            if not nid or nid in seen_ids:
                continue
            seen_ids.add(nid)
            entry = {"id": nid, "label": n.get("label", ""), "properties": n.get("props", {})}
            indirectly_impacted.append(entry)
            _classify_impacted(entry, affected_applications, affected_services, affected_vlans)

    critical_paths = await _build_critical_paths(target_node_ids, action, depth)
    max_criticality = _compute_max_criticality(directly_impacted + indirectly_impacted)

    return {
        "directly_impacted": directly_impacted,
        "indirectly_impacted": indirectly_impacted,
        "affected_applications": affected_applications,
        "affected_services": affected_services,
        "affected_vlans": affected_vlans,
        "total_dependency_count": len(directly_impacted) + len(indirectly_impacted),
        "max_criticality": max_criticality,
        "traversal_strategy": _strategy_name(action),
        "critical_paths": critical_paths,
    }


async def _build_critical_paths(
    target_node_ids: list[str],
    action: str | None,
    depth: int,
) -> list[dict[str, Any]]:
    """Query Neo4j for full dependency paths and deduplicate by endpoint."""
    priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    seen_endpoints: dict[str, dict[str, Any]] = {}

    for node_id in target_node_ids:
        raw_paths = await neo4j_client.get_critical_paths(node_id, action, depth)
        for rp in raw_paths:
            path_nodes = rp.get("path_nodes", [])
            path_edges = rp.get("path_edges", [])
            if len(path_nodes) < 2:
                continue
            endpoint = path_nodes[-1]
            endpoint_id = endpoint.get("id", "")
            if endpoint_id == node_id:
                continue  # loops back to start
            criticality = endpoint.get("props", {}).get("criticality", "low")
            hops = len(path_edges)
            key = f"{node_id}->{endpoint_id}"
            if key not in seen_endpoints or hops < seen_endpoints[key]["hops"]:
                seen_endpoints[key] = {
                    "source_id": node_id,
                    "endpoint_id": endpoint_id,
                    "endpoint_label": endpoint.get("label", ""),
                    "criticality": criticality if isinstance(criticality, str) else "low",
                    "hops": hops,
                    "nodes": [
                        {"id": n.get("id", ""), "label": n.get("label", "")}
                        for n in path_nodes
                    ],
                    "edges": path_edges,
                }

    return sorted(
        seen_endpoints.values(),
        key=lambda p: priority.get(p["criticality"], 0),
        reverse=True,
    )


def _strategy_name(action: str | None) -> str:
    if not action:
        return "generic_neighbor_crawl"
    a = action.lower()
    if a in {"add_rule", "remove_rule", "modify_rule", "disable_rule"}:
        return "rule_dependency_trace"
    if a in {"disable_port", "enable_port", "shutdown_interface"}:
        return "port_dependency_trace"
    if a in {"change_vlan", "delete_vlan", "modify_vlan"}:
        return "vlan_membership_scan"
    if a in {"reboot_device", "decommission", "firmware_upgrade", "delete_sg"}:
        return "full_device_blast_radius"
    if a in {"config_change", "modify_sg"}:
        return "config_neighbor_crawl"
    return "generic_neighbor_crawl"


def _classify_impacted(
    entry: dict[str, Any],
    apps: list[dict[str, Any]],
    services: list[dict[str, Any]],
    vlans: list[dict[str, Any]],
):
    label = entry.get("label", "")
    if label == "Application":
        apps.append(entry)
    elif label == "Service":
        services.append(entry)
    elif label == "VLAN":
        vlans.append(entry)


def _compute_max_criticality(items: list[dict[str, Any]]) -> str:
    priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    max_level = 0
    for item in items:
        props = item.get("properties", {})
        crit = props.get("criticality", "low")
        if isinstance(crit, str):
            max_level = max(max_level, priority.get(crit, 0))
    reverse = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "low"}
    return reverse[max_level]
