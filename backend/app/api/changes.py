from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import Role, require_role
from app.core.security import get_current_user
from app.models.user import User
from app.risk.engine import risk_engine
from app.schemas.change import (
    ChangeCreate,
    ChangeListItem,
    ChangeRead,
    ChangeUpdate,
    RejectRequest,
)
from app.services import change_service, impact_service, policy_service
from app.utils.logging import get_logger
from app.workflow.engine import workflow_engine

logger = get_logger(__name__)
router = APIRouter(prefix="/changes", tags=["changes"])


@router.post("", response_model=ChangeRead, status_code=status.HTTP_201_CREATED)
async def create_change(
    body: ChangeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    change = await change_service.create_change(db, body.model_dump(), current_user.id)
    return change


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
    return change


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
    return updated


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

    impact = await impact_service.analyze_impact(
        target_ids,
        action=change.action,
        change_type=change.change_type,
        environment=change.environment,
        title=change.title,
    )

    # Cache the fresh LLM result
    change.impact_cache = impact

    incident_history_count = await change_service.get_incident_history_count(
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

    await workflow_engine.route_change(db, change, risk_result, current_user.id)

    await db.flush()
    await db.refresh(change)
    return change


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
    return result


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
    return result


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
    return result


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
    return result


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
    return result
