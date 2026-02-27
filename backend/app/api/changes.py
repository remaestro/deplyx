from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import Role, require_role
from app.core.security import get_current_user
from app.graph.neo4j_client import neo4j_client
from app.models.user import User
from app.schemas.change import (
    ChangeCreate,
    ChangeListItem,
    ChangeRead,
    ChangeUpdate,
    RejectRequest,
)
from app.services import change_service, impact_service, policy_service
from app.tasks.analyze_change import enqueue_analysis
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/changes", tags=["changes"])


async def _serialize_change(change):
    enriched_components: list[dict] = []
    for component in change.impacted_components:
        display_value = component.graph_node_id
        label_value = component.component_type
        try:
            rows = await neo4j_client.run_query(
                """
                MATCH (n {id: $id})
                RETURN labels(n)[0] as node_label,
                       n.display_name as display_name,
                       n.name as node_name,
                       n.hostname as hostname
                """,
                {"id": component.graph_node_id},
            )
            if rows:
                row = rows[0]
                display_value = row.get("display_name") or row.get("node_name") or row.get("hostname") or component.graph_node_id
                label_value = row.get("node_label") or component.component_type
        except Exception:
            pass

        enriched_components.append(
            {
                "graph_node_id": component.graph_node_id,
                "component_type": component.component_type,
                "impact_level": component.impact_level,
                "display_name": display_value,
                "label": label_value,
            }
        )

    return {
        "id": change.id,
        "title": change.title,
        "change_type": change.change_type,
        "environment": change.environment,
        "action": change.action,
        "description": change.description,
        "execution_plan": change.execution_plan,
        "rollback_plan": change.rollback_plan,
        "maintenance_window_start": change.maintenance_window_start,
        "maintenance_window_end": change.maintenance_window_end,
        "status": change.status,
        "risk_score": change.risk_score,
        "risk_level": change.risk_level,
        "analysis_stage": change.analysis_stage,
        "analysis_attempts": change.analysis_attempts,
        "analysis_last_error": change.analysis_last_error,
        "analysis_trace_id": change.analysis_trace_id,
        "created_by": change.created_by,
        "reject_reason": change.reject_reason,
        "created_at": change.created_at,
        "updated_at": change.updated_at,
        "impacted_components": enriched_components,
    }


@router.post("", response_model=ChangeRead, status_code=status.HTTP_201_CREATED)
async def create_change(
    body: ChangeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    change = await change_service.create_change(db, body.model_dump(), current_user.id)
    return await _serialize_change(change)


@router.get("", response_model=list[ChangeListItem])
async def list_changes(
    status_filter: str | None = Query(None, alias="status"),
    env: str | None = Query(None),
    change_type: str | None = Query(None, alias="type"),
    mine: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    created_by = current_user.id if mine else None
    changes = await change_service.list_changes(db, status_filter, env, change_type, created_by)
    return changes


@router.get("/{change_id}", response_model=ChangeRead)
async def get_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    return await _serialize_change(change)


@router.put("/{change_id}", response_model=ChangeRead)
async def update_change(
    change_id: str,
    body: ChangeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.created_by != current_user.id and current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Not your change")

    updated = await change_service.update_change(db, change_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=400, detail="Change cannot be edited in current status")
    return await _serialize_change(updated)


@router.delete("/{change_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.created_by != current_user.id and current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Not your change")
    deleted = await change_service.delete_change(db, change_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Only Draft changes can be deleted")


@router.post("/{change_id}/submit", response_model=ChangeRead)
async def submit_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a draft change for analysis and approval."""
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status != "Draft":
        raise HTTPException(status_code=400, detail="Only Draft changes can be submitted")

    if not change.description or not change.description.strip():
        raise HTTPException(status_code=400, detail="Description is required before submit")
    if not change.execution_plan or not change.execution_plan.strip():
        raise HTTPException(status_code=400, detail="Execution plan is required before submit")
    if not change.rollback_plan or not change.rollback_plan.strip():
        raise HTTPException(status_code=400, detail="Rollback plan is required before submit")
    if change.maintenance_window_start is None or change.maintenance_window_end is None:
        raise HTTPException(status_code=400, detail="Maintenance window start and end are required before submit")
    if change.maintenance_window_end <= change.maintenance_window_start:
        raise HTTPException(status_code=400, detail="Maintenance window end must be after start")

    target_ids = [ic.graph_node_id for ic in change.impacted_components if ic.impact_level == "direct"]
    if not target_ids:
        raise HTTPException(status_code=400, detail="At least one target component is required before submit")

    policy_results = await policy_service.evaluate_policies(db, change)
    blocking_reasons = [
        result.reason
        for result in policy_results
        if result.triggered and result.action == "block" and result.reason
    ]
    if blocking_reasons:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Change blocked by policy",
                "reasons": blocking_reasons,
            },
        )

    change = await change_service.transition_status(db, change_id, "Pending")
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    await change_service.set_analysis_stage(db, change_id, "pending", error=None)
    try:
        enqueue_analysis(change_id=change_id)
    except Exception:
        logger.warning("Failed to enqueue analysis for change %s – Celery/Redis may be unavailable", change_id)
    await db.refresh(change)
    return await _serialize_change(change)


@router.get("/{change_id}/stage")
async def get_change_stage(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    return {
        "change_id": change.id,
        "analysis_stage": change.analysis_stage,
        "analysis_attempts": change.analysis_attempts,
        "analysis_last_error": change.analysis_last_error,
        "analysis_trace_id": change.analysis_trace_id,
    }


@router.get("/{change_id}/impact")
async def get_change_impact(
    change_id: str,
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")

    # Return cached impact if available (unless ?refresh=true)
    if change.impact_cache and not refresh:
        logger.info("[IMPACT-API] CACHE HIT for change %s (llm_powered=%s)",
                    change_id, change.impact_cache.get('llm_powered', '?'))
        return {"change_id": change_id, "impact": change.impact_cache}

    logger.info("[IMPACT-API] CACHE MISS for change %s (refresh=%s, has_cache=%s)",
                change_id, refresh, bool(change.impact_cache))
    target_ids = [ic.graph_node_id for ic in change.impacted_components if ic.impact_level == "direct"]
    logger.info("[IMPACT-API] Running fresh analysis for %s: targets=%s, action=%s",
                change_id, target_ids, change.action)
    impact = await impact_service.analyze_impact(
        target_ids,
        action=change.action,
        change_type=change.change_type,
        environment=change.environment,
        title=change.title,
    )

    # Persist to cache
    change.impact_cache = impact
    await db.flush()

    return {"change_id": change_id, "impact": impact}


@router.post("/{change_id}/approve", response_model=ChangeRead)
async def approve_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.APPROVER, Role.NETWORK, Role.SECURITY, Role.DC_MANAGER)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status not in ("Pending", "Analyzing"):
        raise HTTPException(status_code=400, detail="Change not in approvable state")

    result = await change_service.transition_status(db, change_id, "Approved")
    return await _serialize_change(result)


@router.post("/{change_id}/reject", response_model=ChangeRead)
async def reject_change(
    change_id: str,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.APPROVER, Role.NETWORK, Role.SECURITY, Role.DC_MANAGER)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status not in ("Pending", "Analyzing"):
        raise HTTPException(status_code=400, detail="Change not in rejectable state")

    result = await change_service.transition_status(db, change_id, "Rejected", reject_reason=body.reason)
    return await _serialize_change(result)


@router.post("/{change_id}/execute", response_model=ChangeRead)
async def execute_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status != "Approved":
        raise HTTPException(status_code=400, detail="Only approved changes can be executed")

    result = await change_service.transition_status(db, change_id, "Executing")
    return await _serialize_change(result)


@router.post("/{change_id}/complete", response_model=ChangeRead)
async def complete_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status != "Executing":
        raise HTTPException(status_code=400, detail="Only executing changes can be completed")

    result = await change_service.transition_status(db, change_id, "Completed")
    return await _serialize_change(result)


@router.post("/{change_id}/rollback", response_model=ChangeRead)
async def rollback_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status not in ("Executing", "Completed"):
        raise HTTPException(status_code=400, detail="Change cannot be rolled back")

    result = await change_service.transition_status(db, change_id, "RolledBack")
    return await _serialize_change(result)
