from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.risk.engine import risk_engine
from app.services import change_service, impact_service

router = APIRouter(prefix="/risk", tags=["risk"])


class RiskCalculateRequest(BaseModel):
    change_id: str


@router.post("/calculate")
async def calculate_risk(
    body: RiskCalculateRequest | None = None,
    change_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Run impact analysis + risk scoring for a change. Updates the change record."""
    resolved_change_id = body.change_id if body is not None else change_id
    if not resolved_change_id:
        raise HTTPException(status_code=400, detail="change_id is required")

    change = await change_service.get_change(db, resolved_change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")

    # Gather target component IDs
    target_ids = [ic.graph_node_id for ic in change.impacted_components if ic.impact_level == "direct"]

    # Run impact analysis (action-aware + LLM)
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

    # Run risk scoring
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

    # Update change with risk assessment
    change.risk_score = risk_result["risk_score"]
    change.risk_level = risk_result["risk_level"]
    if change.status == "Pending":
        change.status = "Analyzing"
    await db.flush()
    await db.refresh(change)

    return {
        "change_id": change.id,
        "impact": impact,
        "risk": risk_result,
    }
