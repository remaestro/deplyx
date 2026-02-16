from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.audit import AuditLog
from app.models.change import Change, ChangeImpactedComponent


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=None)
    return dt


async def get_kpis(db: AsyncSession) -> dict:
    changes_result = await db.execute(select(Change))
    changes = list(changes_result.scalars().all())

    approvals_result = await db.execute(select(Approval))
    approvals = list(approvals_result.scalars().all())

    audits_result = await db.execute(select(AuditLog))
    audits = list(audits_result.scalars().all())

    impacted_result = await db.execute(select(ChangeImpactedComponent))
    impacted = list(impacted_result.scalars().all())

    total_changes = len(changes)
    non_draft_changes = [c for c in changes if c.status != "Draft"]
    denominator = len(non_draft_changes) or total_changes or 1

    auto_approved_count = sum(1 for a in audits if a.action == "auto_approved")
    auto_approved_pct = round((auto_approved_count / denominator) * 100, 1)

    approvals_by_change: dict[str, list[Approval]] = defaultdict(list)
    for approval in approvals:
        approvals_by_change[approval.change_id].append(approval)

    validation_durations: list[float] = []
    for change_id, items in approvals_by_change.items():
        if not items:
            continue
        if any(item.decided_at is None for item in items):
            continue
        created_at = min(item.created_at for item in items)
        decided_at = max(item.decided_at for item in items if item.decided_at is not None)
        if created_at and decided_at:
            minutes = (_to_utc(decided_at) - _to_utc(created_at)).total_seconds() / 60
            if minutes >= 0:
                validation_durations.append(minutes)

    avg_validation_minutes = round(sum(validation_durations) / len(validation_durations), 1) if validation_durations else None

    completed_or_rolled = [c for c in changes if c.status in ("Completed", "RolledBack")]
    rolled_back_count = sum(1 for c in completed_or_rolled if c.status == "RolledBack")
    incidents_post_change_pct = round((rolled_back_count / len(completed_or_rolled)) * 100, 1) if completed_or_rolled else 0.0

    # Precision proxy: among changes predicted as incident-prone (risk_level=high),
    # how many actually ended with an incident proxy (RolledBack).
    predicted_incident = [c for c in completed_or_rolled if (c.risk_level or "").lower() == "high"]
    true_positive_incidents = sum(1 for c in predicted_incident if c.status == "RolledBack")
    scoring_precision_pct = (
        round((true_positive_incidents / len(predicted_incident)) * 100, 1)
        if predicted_incident
        else 0.0
    )

    direct_impacted_by_change: dict[str, list[ChangeImpactedComponent]] = defaultdict(list)
    for item in impacted:
        if item.impact_level == "direct":
            direct_impacted_by_change[item.change_id].append(item)

    core_detected_count = 0
    for change_id, items in direct_impacted_by_change.items():
        if any(("CORE" in i.graph_node_id.upper()) or i.graph_node_id.upper().startswith("FW-") for i in items):
            core_detected_count += 1
    core_detected_pct = round((core_detected_count / denominator) * 100, 1)

    definitions = {
        "auto_approved_pct": "Share of non-draft changes auto-approved by workflow (audit action: auto_approved).",
        "avg_validation_minutes": "Mean elapsed minutes from first approval request creation to final approval decision per change.",
        "incidents_post_change_pct": "Proxy metric: percentage of closed changes ending in RolledBack status.",
        "scoring_precision_pct": "Proxy precision: among closed changes predicted high-risk, percentage that ended in RolledBack status.",
        "core_changes_detected_pct": "Share of non-draft changes with direct targets matching core identifiers (CORE* or FW-*).",
    }

    return {
        "total_changes": total_changes,
        "auto_approved_pct": auto_approved_pct,
        "avg_validation_minutes": avg_validation_minutes,
        "incidents_post_change_pct": incidents_post_change_pct,
        "scoring_precision_pct": scoring_precision_pct,
        "core_changes_detected_pct": core_detected_pct,
        "definitions": definitions,
    }
