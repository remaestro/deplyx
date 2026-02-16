"""Policy API — CRUD + evaluate policies against changes."""

import random
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import Role, require_role
from app.models.user import User
from app.schemas.policy import (
    PolicyCreate,
    PolicyEvaluationResponse,
    PolicyRead,
    PolicyUpdate,
)
from app.services import policy_service
from app.services.change_service import get_change

router = APIRouter(prefix="/policies", tags=["policies"])


@router.post("", response_model=PolicyRead, status_code=201)
async def create_policy(
    body: PolicyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.ADMIN, Role.SECURITY)),
):
    policy = await policy_service.create_policy(db, body, user.id)
    return policy


@router.get("", response_model=list[PolicyRead])
async def list_policies(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.ADMIN, Role.SECURITY, Role.VIEWER)),
):
    return await policy_service.list_policies(db, enabled_only=enabled_only)


@router.get("/{policy_id}", response_model=PolicyRead)
async def get_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.ADMIN, Role.SECURITY, Role.VIEWER)),
):
    p = await policy_service.get_policy(db, policy_id)
    if p is None:
        raise HTTPException(404, "Policy not found")
    return p


@router.put("/{policy_id}", response_model=PolicyRead)
async def update_policy(
    policy_id: int,
    body: PolicyUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.ADMIN, Role.SECURITY)),
):
    p = await policy_service.update_policy(db, policy_id, body)
    if p is None:
        raise HTTPException(404, "Policy not found")
    return p


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.ADMIN)),
):
    ok = await policy_service.delete_policy(db, policy_id)
    if not ok:
        raise HTTPException(404, "Policy not found")


@router.post("/evaluate", response_model=PolicyEvaluationResponse)
async def evaluate_policies(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.ADMIN, Role.SECURITY, Role.APPROVER)),
):
    """Evaluate all enabled policies against a specific change."""
    change_id = body.get("change_id")
    if not change_id:
        raise HTTPException(400, "change_id is required")
    change = await get_change(db, str(change_id))
    if change is None:
        raise HTTPException(404, "Change not found")

    results = await policy_service.evaluate_policies(db, change)

    blocked = any(r.triggered and r.action == "block" for r in results)
    warnings = [r.reason for r in results if r.triggered and r.action == "warn" and r.reason]

    return PolicyEvaluationResponse(
        change_id=change.id,
        results=results,
        blocked=blocked,
        warnings=warnings,
    )


@router.post("/{policy_id}/simulate")
async def simulate_policy(
    policy_id: int,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.ADMIN, Role.SECURITY)),
):
    """Simulate a policy against a mock change payload.

    Returns whether the change would be blocked, which rules matched,
    and the risk delta.  This is a stub — wire up real evaluation later.
    """
    p = await policy_service.get_policy(db, policy_id)
    if p is None:
        raise HTTPException(404, "Policy not found")

    # Stub simulation logic
    would_block = random.random() > 0.4
    return {
        "would_block": would_block,
        "matched_rules": [p.rule_type, "env_scope_match"],
        "risk_delta": round(random.uniform(-15, 15), 1),
    }


@router.get("/conflicts")
async def detect_policy_conflicts(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.ADMIN, Role.SECURITY)),
):
    """Detect conflicting policies.

    Stub implementation — returns example conflicts.  Replace with real
    overlap / precedence analysis once the evaluation engine is enriched.
    """
    policies = await policy_service.list_policies(db, enabled_only=True)
    conflicts: list[dict] = []

    # Naïve pairwise check: two policies targeting the same environment
    # with contradicting actions.
    for i, a in enumerate(policies):
        for b in policies[i + 1:]:
            env_a = set(a.condition.get("environments", []) if isinstance(a.condition, dict) else [])
            env_b = set(b.condition.get("environments", []) if isinstance(b.condition, dict) else [])
            if env_a & env_b and a.action != b.action:
                conflicts.append({
                    "policy_a": a.name,
                    "policy_b": b.name,
                    "conflict_type": "overlap",
                    "description": (
                        f"Both target environments {', '.join(env_a & env_b)} "
                        f"but '{a.name}' uses action '{a.action}' while "
                        f"'{b.name}' uses action '{b.action}'."
                    ),
                })

    return conflicts
