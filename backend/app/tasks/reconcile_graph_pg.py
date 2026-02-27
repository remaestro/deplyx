from datetime import UTC, datetime

from sqlalchemy import distinct, func, select

from app.celery_app import celery_app, run_async
from app.graph.neo4j_client import neo4j_client
from app.models.change import ChangeImpactedComponent
from app.models.connector import Connector
from app.utils.logging import get_logger

logger = get_logger(__name__)

_LAST_DRIFT_COUNT = 0



def get_last_drift_count() -> int:
    return _LAST_DRIFT_COUNT


@celery_app.task(name="app.tasks.reconcile_graph_pg")
def reconcile_graph_pg() -> dict:
    """Compare PG and Neo4j node counts + per-connector drift check.

    For each active connector we compare the count of graph nodes whose id
    prefix matches the vendor pattern against the last_sync_detail stored in
    PG after the most recent sync.
    """

    async def _do():
        global _LAST_DRIFT_COUNT
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            # Global drift (as before)
            result = await db.execute(select(func.count(distinct(ChangeImpactedComponent.graph_node_id))))
            pg_distinct_nodes = int(result.scalar() or 0)

            topo = await neo4j_client.get_full_topology()
            graph_nodes = len(topo.get("nodes", []))

            drift_count = abs(pg_distinct_nodes - graph_nodes)
            _LAST_DRIFT_COUNT = drift_count

            # Per-connector drift
            connector_drifts: list[dict] = []
            conn_result = await db.execute(
                select(Connector).where(Connector.status == "active")
            )
            connectors = list(conn_result.scalars().all())

            for conn in connectors:
                detail = conn.last_sync_detail or {}
                synced = detail.get("synced", {})
                expected_total = sum(synced.values()) if synced else 0
                # Simple heuristic: count graph nodes matching connector type prefix
                prefix_map = {
                    "paloalto": "PA-",
                    "fortinet": "FG-",
                    "cisco": "CISCO-",
                    "checkpoint": "CP-",
                    "juniper": "JUN-",
                    "aruba-switch": "ARUBA-SW-",
                    "aruba-ap": "ARUBA-AP-",
                    "cisco-nxos": "NXOS-",
                    "cisco-router": "ROUTER-",
                    "cisco-wlc": "WLC-",
                    "vyos": "VYOS-",
                    "strongswan": "VPN-",
                    "snort": "IDS-",
                    "openldap": "LDAP-",
                    "nginx": "NGINX-",
                    "postgres": "PG-",
                    "redis": "REDIS-",
                    "elasticsearch": "ES-",
                    "grafana": "GRAFANA-",
                    "prometheus": "PROM-",
                }
                prefix = prefix_map.get(conn.connector_type, "")
                if prefix:
                    actual_count = sum(
                        1 for n in topo.get("nodes", [])
                        if str(n.get("id", "")).startswith(prefix)
                    )
                    connector_drifts.append({
                        "connector_id": conn.id,
                        "type": conn.connector_type,
                        "expected": expected_total,
                        "actual_graph": actual_count,
                        "drift": abs(expected_total - actual_count),
                    })

            return {
                "pg_distinct_nodes": pg_distinct_nodes,
                "graph_nodes": graph_nodes,
                "drift_count": drift_count,
                "connector_drifts": connector_drifts,
                "checked_at": datetime.now(UTC).isoformat(),
            }

    return run_async(_do())
