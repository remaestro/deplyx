"""Simulation service — answers "what if" questions about rule changes."""

from typing import Any

from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def simulate_rule_removal(rule_id: str) -> dict[str, Any]:
    """Simulate removing a firewall rule and determine what breaks."""

    rule = await neo4j_client.get_node("Rule", rule_id)
    if rule is None:
        return {"error": f"Rule {rule_id} not found"}

    # Find applications this rule PROTECTS
    cypher_apps = """
    MATCH (r:Rule {id: $rule_id})-[:PROTECTS]->(app:Application)
    RETURN app.id as id, app.name as name, app.criticality as criticality
    """
    affected_apps = await neo4j_client.run_query(cypher_apps, {"rule_id": rule_id})

    # Find the device that owns this rule
    cypher_device = """
    MATCH (d:Device)-[:HAS_RULE]->(r:Rule {id: $rule_id})
    RETURN d.id as id, d.hostname as hostname, d.type as type
    """
    owner_devices = await neo4j_client.run_query(cypher_device, {"rule_id": rule_id})

    # Determine blocked flows based on rule source/destination
    blocked_flows: list[dict[str, Any]] = []
    affected_vlans: list[dict[str, Any]] = []
    if rule:
        src = rule.get("source", "any")
        dst = rule.get("destination", "any")
        port = rule.get("port", "any")
        proto = rule.get("protocol", "any")
        action = rule.get("action", "allow")

        if action == "allow":
            blocked_flows.append({
                "flow": f"{src} → {dst}:{port}/{proto}",
                "impact": "This traffic will be BLOCKED if rule is removed",
            })

            # Find VLANs in source/dest ranges
            if dst != "any":
                cypher_vlans = """
                MATCH (v:VLAN)-[:ROUTES_TO]->(app:Application)<-[:PROTECTS]-(r:Rule {id: $rule_id})
                RETURN DISTINCT v.id as id, v.name as name
                """
                affected_vlans = await neo4j_client.run_query(cypher_vlans, {"rule_id": rule_id})
            else:
                affected_vlans = []
        else:
            # It's a deny rule — removing it would OPEN traffic
            blocked_flows.append({
                "flow": f"{src} → {dst}:{port}/{proto}",
                "impact": "WARNING: Removing this DENY rule will OPEN this traffic path",
            })
            affected_vlans = []

    inaccessible_apps = [
        {"id": app["id"], "name": app["name"], "criticality": app.get("criticality", "medium")}
        for app in affected_apps
    ]

    return {
        "rule": rule,
        "owner_devices": owner_devices,
        "blocked_flows": blocked_flows,
        "inaccessible_apps": inaccessible_apps,
        "affected_vlans": affected_vlans if affected_vlans is not None else [],
        "severity": "critical" if any(a.get("criticality") == "critical" for a in affected_apps) else "high" if affected_apps else "low",
    }


async def simulate_rule_change(rule_id: str, new_params: dict[str, Any]) -> dict[str, Any]:
    """Simulate changing a rule's parameters and show the diff/impact."""

    rule = await neo4j_client.get_node("Rule", rule_id)
    if rule is None:
        return {"error": f"Rule {rule_id} not found"}

    # Build before/after comparison
    before = {
        "source": rule.get("source", "any"),
        "destination": rule.get("destination", "any"),
        "port": rule.get("port", "any"),
        "protocol": rule.get("protocol", "any"),
        "action": rule.get("action", "allow"),
    }

    after = {**before}
    for k, v in new_params.items():
        if k in after:
            after[k] = v

    changes: list[dict[str, Any]] = []
    for key in before:
        if before[key] != after[key]:
            changes.append({"field": key, "before": before[key], "after": after[key]})

    # Detect if the change narrows or widens the rule
    risk_notes: list[str] = []
    if after["source"] == "any" and before["source"] != "any":
        risk_notes.append("WARNING: Source changed to 'any' — this widens the rule scope")
    if after["destination"] == "any" and before["destination"] != "any":
        risk_notes.append("WARNING: Destination changed to 'any' — this widens the rule scope")
    if after["action"] == "allow" and before["action"] == "deny":
        risk_notes.append("CRITICAL: Changing from DENY to ALLOW opens previously blocked traffic")
    if after["source"] == "any" and after["destination"] == "any" and after["port"] == "any":
        risk_notes.append("CRITICAL: This creates an ANY-ANY rule")

    # Find apps affected by this rule
    cypher_apps = """
    MATCH (r:Rule {id: $rule_id})-[:PROTECTS]->(app:Application)
    RETURN app.id as id, app.name as name, app.criticality as criticality
    """
    affected_apps = await neo4j_client.run_query(cypher_apps, {"rule_id": rule_id})

    return {
        "rule_id": rule_id,
        "before": before,
        "after": after,
        "changes": changes,
        "risk_notes": risk_notes,
        "affected_applications": affected_apps,
    }
