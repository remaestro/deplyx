"""Simulation API — "what-if" analysis for rule changes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.rbac import Role, require_role
from app.models.user import User
from app.services.simulation_service import simulate_rule_change, simulate_rule_removal

router = APIRouter(prefix="/simulation", tags=["simulation"])


class RuleChangeRequest(BaseModel):
    rule_id: str
    new_params: dict = {}


@router.post("/rule-removal")
async def api_simulate_rule_removal(
    body: dict,
    _user: User = Depends(require_role(Role.ADMIN, Role.NETWORK, Role.SECURITY)),
):
    """Simulate the impact of removing a firewall rule."""
    rule_id = body.get("rule_id")
    if not rule_id:
        return {"error": "rule_id is required"}
    result = await simulate_rule_removal(rule_id)
    return result


@router.post("/rule-change")
async def api_simulate_rule_change(
    body: RuleChangeRequest,
    _user: User = Depends(require_role(Role.ADMIN, Role.NETWORK, Role.SECURITY)),
):
    """Simulate the impact of changing a firewall rule's parameters."""
    result = await simulate_rule_change(body.rule_id, body.new_params)
    return result
