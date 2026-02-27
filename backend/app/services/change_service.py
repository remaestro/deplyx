from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.graph.neo4j_client import neo4j_client
from app.models.change import Change, ChangeImpactedComponent
from app.risk.engine import risk_engine
from app.services import impact_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _resolve_component_type(node_id: str) -> str:
    try:
        node = await neo4j_client.get_node("Device", node_id)
        if node:
            return "Device"
        for label in ["Rule", "VLAN", "Application", "Interface", "Service", "Datacenter", "IP"]:
            node = await neo4j_client.get_node(label, node_id)
            if node:
                return label
    except Exception:
        logger.debug("Neo4j unavailable – cannot resolve component type for %s", node_id)
    return ""


async def _build_impacted_components(target_components: list[str], depth: int = 2, action: str | None = None) -> list[dict[str, str]]:
    all_impacted: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for comp_id in target_components:
        if comp_id in seen_ids:
            continue
        seen_ids.add(comp_id)
        all_impacted.append(
            {
                "graph_node_id": comp_id,
                "component_type": await _resolve_component_type(comp_id),
                "impact_level": "direct",
            }
        )

        # Use action-aware neighbor traversal
        try:
            neighbors = await neo4j_client.get_action_aware_neighbors(comp_id, action=action, depth=depth)
        except Exception:
            logger.debug("Neo4j unavailable – skipping neighbor traversal for %s", comp_id)
            neighbors = []
        for neighbor in neighbors:
            neighbor_id = neighbor.get("id")
            if not neighbor_id or neighbor_id in seen_ids:
                continue
            seen_ids.add(neighbor_id)
            all_impacted.append(
                {
                    "graph_node_id": neighbor_id,
                    "component_type": neighbor.get("label", ""),
                    "impact_level": "indirect",
                }
            )

    return all_impacted


async def create_change(db: AsyncSession, data: dict[str, Any], user_id: int) -> Change:
    target_components = data.pop("target_components", [])

    change = Change(**data, created_by=user_id)
    db.add(change)
    await db.flush()

    impacted_components = await _build_impacted_components(target_components, depth=2, action=change.action)

    for comp in impacted_components:
        ic = ChangeImpactedComponent(change_id=change.id, **comp)
        db.add(ic)

    await db.flush()
    await db.refresh(change)
    await db.refresh(change, ["impacted_components"])
    return change


async def get_change(db: AsyncSession, change_id: str) -> Change | None:
    result = await db.execute(
        select(Change)
        .options(selectinload(Change.impacted_components))
        .where(Change.id == change_id)
    )
    return result.scalar_one_or_none()


async def list_changes(
    db: AsyncSession,
    status_filter: str | None = None,
    env_filter: str | None = None,
    type_filter: str | None = None,
    created_by: int | None = None,
) -> list[Change]:
    stmt = select(Change).order_by(Change.created_at.desc())
    if status_filter:
        stmt = stmt.where(Change.status == status_filter)
    if env_filter:
        stmt = stmt.where(Change.environment == env_filter)
    if type_filter:
        stmt = stmt.where(Change.change_type == type_filter)
    if created_by is not None:
        stmt = stmt.where(Change.created_by == created_by)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_change(db: AsyncSession, change_id: str, data: dict[str, Any]) -> Change | None:
    change = await get_change(db, change_id)
    if change is None:
        return None
    if change.status not in ("Draft", "Pending"):
        return None  # Can only edit draft/pending

    target_components = data.pop("target_components", None)

    # Track if fields affecting impact analysis changed
    invalidate_impact = False
    for key, value in data.items():
        if value is not None:
            if key in ("action", "change_type", "environment", "title"):
                invalidate_impact = True
            setattr(change, key, value)

    if target_components is not None:
        invalidate_impact = True
        # Replace impacted components
        for ic in change.impacted_components:
            await db.delete(ic)
        await db.flush()

        impacted_components = await _build_impacted_components(target_components, depth=2, action=change.action)
        for comp in impacted_components:
            ic = ChangeImpactedComponent(change_id=change.id, **comp)
            db.add(ic)

    # Clear stale impact cache if relevant fields changed
    if invalidate_impact and change.impact_cache is not None:
        change.impact_cache = None

    await db.flush()
    await db.refresh(change)
    await db.refresh(change, ["impacted_components"])
    return change


async def delete_change(db: AsyncSession, change_id: str) -> bool:
    change = await get_change(db, change_id)
    if change is None or change.status != "Draft":
        return False
    await db.delete(change)
    await db.flush()
    return True


async def transition_status(db: AsyncSession, change_id: str, new_status: str, **kwargs) -> Change | None:
    change = await get_change(db, change_id)
    if change is None:
        return None
    change.status = new_status
    for k, v in kwargs.items():
        if hasattr(change, k):
            setattr(change, k, v)
    await db.flush()
    await db.refresh(change)
    return change


async def set_analysis_stage(
    db: AsyncSession,
    change_id: str,
    stage: str,
    error: str | None = None,
    trace_id: str | None = None,
) -> Change | None:
    change = await get_change(db, change_id)
    if change is None:
        return None
    change.analysis_stage = stage
    if error is not None:
        change.analysis_last_error = error
    if trace_id is not None:
        change.analysis_trace_id = trace_id
    await db.flush()
    await db.refresh(change)
    return change


async def set_analysis_last_error(db: AsyncSession, change_id: str, error: str | None) -> Change | None:
    change = await get_change(db, change_id)
    if change is None:
        return None
    change.analysis_last_error = error
    await db.flush()
    await db.refresh(change)
    return change


async def increment_analysis_attempts(db: AsyncSession, change_id: str) -> Change | None:
    change = await get_change(db, change_id)
    if change is None:
        return None
    change.analysis_attempts = int(change.analysis_attempts or 0) + 1
    await db.flush()
    await db.refresh(change)
    return change


async def get_incident_history_count(
    db: AsyncSession,
    target_component_ids: list[str],
    exclude_change_id: str | None = None,
) -> int:
    if not target_component_ids:
        return 0

    stmt = (
        select(Change.id)
        .join(ChangeImpactedComponent, ChangeImpactedComponent.change_id == Change.id)
        .where(
            Change.status == "RolledBack",
            ChangeImpactedComponent.graph_node_id.in_(target_component_ids),
        )
        .distinct()
    )

    if exclude_change_id:
        stmt = stmt.where(Change.id != exclude_change_id)

    result = await db.execute(stmt)
    return len(result.scalars().all())


async def invalidate_all_change_analysis(db: AsyncSession, reason: str | None = None) -> int:
    result = await db.execute(select(Change))
    changes = list(result.scalars().all())

    for change in changes:
        change.impact_cache = None
        change.risk_score = None
        change.risk_level = None

    await db.flush()
    logger.info("Invalidated analysis for %d changes (reason=%s)", len(changes), reason or "n/a")
    return len(changes)


async def enqueue_analysis_for_all_changes(db: AsyncSession) -> int:
    result = await db.execute(select(Change).options(selectinload(Change.impacted_components)))
    changes = list(result.scalars().all())
    recomputed = 0

    for change in changes:
        target_ids = [
            ic.graph_node_id for ic in change.impacted_components if ic.impact_level == "direct"
        ]
        if not target_ids:
            continue

        impact = await impact_service.analyze_impact(
            target_ids,
            action=change.action,
            change_type=change.change_type,
            environment=change.environment,
            title=change.title,
        )
        change.impact_cache = impact

        incident_history_count = await get_incident_history_count(
            db,
            target_ids,
            exclude_change_id=change.id,
        )

        change_data = {
            "environment": change.environment,
            "rollback_plan": change.rollback_plan,
            "maintenance_window_start": change.maintenance_window_start,
            "maintenance_window_end": change.maintenance_window_end,
            "target_components": target_ids,
            "incident_history_count": incident_history_count,
            "action": change.action,
        }
        risk_result = await risk_engine.evaluate_change(change_data, impact)
        change.risk_score = risk_result["risk_score"]
        change.risk_level = risk_result["risk_level"]
        recomputed += 1

    await db.flush()
    logger.info("Recomputed analysis for %d changes", recomputed)
    return recomputed
