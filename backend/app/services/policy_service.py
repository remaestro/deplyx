"""Policy service — CRUD + automated policy evaluation against changes."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy
from app.schemas.policy import (
    PolicyCreate,
    PolicyEvaluationResult,
    PolicyUpdate,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_env(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().lower()
    env_aliases = {
        "prod": "production",
        "production": "production",
        "preprod": "preprod",
        "staging": "preprod",
        "dc1": "dc1",
        "dc2": "dc2",
        "development": "development",
        "dev": "development",
        "lab": "lab",
    }
    return env_aliases.get(normalized, normalized)


def _normalize_change_type(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().lower()
    type_aliases = {
        "firewall": "firewall_rule",
        "firewall_rule": "firewall_rule",
        "acl": "acl",
        "switch": "switch",
        "vlan": "vlan",
        "port": "port",
        "interface": "interface",
        "rack": "rack",
        "cloudsg": "cloudsg",
        "routing": "routing",
        "other": "other",
    }
    return type_aliases.get(normalized, normalized)


async def create_policy(db: AsyncSession, data: PolicyCreate, user_id: int) -> Policy:
    policy = Policy(
        name=data.name,
        description=data.description,
        rule_type=data.rule_type.value,
        condition=data.condition,
        action=data.action.value,
        enabled=data.enabled,
        created_by=user_id,
    )
    db.add(policy)
    await db.flush()
    await db.refresh(policy)
    return policy


async def get_policy(db: AsyncSession, policy_id: int) -> Policy | None:
    return await db.get(Policy, policy_id)


async def list_policies(db: AsyncSession, enabled_only: bool = False) -> list[Policy]:
    stmt = select(Policy).order_by(Policy.id)
    if enabled_only:
        stmt = stmt.where(Policy.enabled.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_policy(db: AsyncSession, policy_id: int, data: PolicyUpdate) -> Policy | None:
    policy = await db.get(Policy, policy_id)
    if policy is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        if hasattr(value, "value"):
            value = value.value
        setattr(policy, field, value)
    await db.flush()
    await db.refresh(policy)
    return policy


async def delete_policy(db: AsyncSession, policy_id: int) -> bool:
    policy = await db.get(Policy, policy_id)
    if policy is None:
        return False
    await db.delete(policy)
    await db.flush()
    return True


# ── Evaluation logic ──────────────────────────────────────────────

async def evaluate_policies(db: AsyncSession, change) -> list[PolicyEvaluationResult]:
    """Run all enabled policies against a Change object.

    Returns a list of evaluation results, one per policy.
    """
    policies = await list_policies(db, enabled_only=True)
    results: list[PolicyEvaluationResult] = []

    for policy in policies:
        result = _evaluate_single(policy, change)
        results.append(result)

    return results


def _evaluate_single(policy: Policy, change) -> PolicyEvaluationResult:
    """Evaluate a single policy rule against a change."""
    handler = _HANDLERS.get(policy.rule_type)
    if handler is None:
        return PolicyEvaluationResult(
            policy_id=policy.id,
            policy_name=policy.name,
            rule_type=policy.rule_type,
            triggered=False,
            action=policy.action,
            reason=f"Unknown rule_type '{policy.rule_type}'",
        )
    return handler(policy, change)


# ── Individual policy type handlers ───────────────────────────────

def _check_time_restriction(policy: Policy, change) -> PolicyEvaluationResult:
    """Block changes to core infrastructure during business hours.

    Condition schema example:
        {"blocked_hours_start": 8, "blocked_hours_end": 18,
         "blocked_days": [0,1,2,3,4],  # Mon-Fri
         "environments": ["production"]}
    """
    cond = policy.condition or {}
    blocked_start = cond.get("blocked_hours_start", 8)
    blocked_end = cond.get("blocked_hours_end", 18)
    blocked_days = cond.get("blocked_days", [0, 1, 2, 3, 4])
    envs = [_normalize_env(e) for e in cond.get("environments", ["production"])]

    # Check if the change targets the restricted environment
    change_env = _normalize_env(getattr(change, "environment", None))
    if change_env and change_env not in envs:
        return PolicyEvaluationResult(
            policy_id=policy.id,
            policy_name=policy.name,
            rule_type=policy.rule_type,
            triggered=False,
            action=policy.action,
            reason="Environment not restricted by this policy",
        )

    # Check maintenance window timing
    mw_start = getattr(change, "maintenance_window_start", None)
    now = mw_start or datetime.now(timezone.utc)
    if now.weekday() in blocked_days and blocked_start <= now.hour < blocked_end:
        return PolicyEvaluationResult(
            policy_id=policy.id,
            policy_name=policy.name,
            rule_type=policy.rule_type,
            triggered=True,
            action=policy.action,
            reason=f"Change scheduled during blocked business hours ({blocked_start}:00-{blocked_end}:00 on weekdays)",
        )

    return PolicyEvaluationResult(
        policy_id=policy.id,
        policy_name=policy.name,
        rule_type=policy.rule_type,
        triggered=False,
        action=policy.action,
        reason="Change is outside blocked hours",
    )


def _check_double_validation(policy: Policy, change) -> PolicyEvaluationResult:
    """Require double approval for changes in sensitive zones.

    Condition schema example:
        {"environments": ["production"],
         "change_types": ["firewall_rule", "acl"],
         "required_approvals": 2}
    """
    cond = policy.condition or {}
    envs = [_normalize_env(e) for e in cond.get("environments", ["production"])]
    change_types = [_normalize_change_type(t) for t in cond.get("change_types", [])]

    change_env = _normalize_env(getattr(change, "environment", None))
    change_type = _normalize_change_type(getattr(change, "change_type", None))

    env_match = change_env in envs if change_env else False
    type_match = change_type in change_types if (change_type and change_types) else True

    if env_match and type_match:
        required = cond.get("required_approvals", 2)
        return PolicyEvaluationResult(
            policy_id=policy.id,
            policy_name=policy.name,
            rule_type=policy.rule_type,
            triggered=True,
            action=policy.action,
            reason=f"Double validation required: {required} approvals needed for {change_type} in {change_env}",
        )

    return PolicyEvaluationResult(
        policy_id=policy.id,
        policy_name=policy.name,
        rule_type=policy.rule_type,
        triggered=False,
        action=policy.action,
        reason="Change does not match double validation criteria",
    )


def _check_auto_block(policy: Policy, change) -> PolicyEvaluationResult:
    """Automatically block changes that violate security posture.

    Condition schema example:
        {"block_any_any_rules": true,
         "block_environments": ["production"],
         "block_change_types": ["firewall_rule"]}
    """
    cond = policy.condition or {}
    block_envs = [_normalize_env(e) for e in cond.get("block_environments", ["production"])]
    block_types = [_normalize_change_type(t) for t in cond.get("block_change_types", [])]
    block_any_any = cond.get("block_any_any_rules", True)

    change_env = _normalize_env(getattr(change, "environment", None))
    change_type = _normalize_change_type(getattr(change, "change_type", None))
    description = getattr(change, "description", "") or ""
    execution_plan = getattr(change, "execution_plan", "") or ""
    combined_text = (description + " " + execution_plan).lower()

    env_match = change_env in block_envs if change_env else False
    type_match = change_type in block_types if (change_type and block_types) else False

    # Check for ANY-ANY rule patterns
    if block_any_any and ("any" in combined_text and ("source" in combined_text or "destination" in combined_text or "0.0.0.0" in combined_text)):
        return PolicyEvaluationResult(
            policy_id=policy.id,
            policy_name=policy.name,
            rule_type=policy.rule_type,
            triggered=True,
            action=policy.action,
            reason="AUTO-BLOCK: Change appears to create an ANY-ANY rule which violates security policy",
        )

    if env_match and type_match:
        return PolicyEvaluationResult(
            policy_id=policy.id,
            policy_name=policy.name,
            rule_type=policy.rule_type,
            triggered=True,
            action=policy.action,
            reason=f"AUTO-BLOCK: {change_type} changes in {change_env} are blocked by policy",
        )

    return PolicyEvaluationResult(
        policy_id=policy.id,
        policy_name=policy.name,
        rule_type=policy.rule_type,
        triggered=False,
        action=policy.action,
        reason="Change does not match auto-block criteria",
    )


_HANDLERS = {
    "time_restriction": _check_time_restriction,
    "double_validation": _check_double_validation,
    "auto_block": _check_auto_block,
}
