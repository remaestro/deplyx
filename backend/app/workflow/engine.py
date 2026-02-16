"""Intelligent workflow engine — routes changes based on risk scoring.

Routing logic:
  - Low risk (0–30):    auto-approve → no approval records needed
  - Medium risk (31–70): targeted approval → route to relevant role leads
  - High risk (71+):     CAB required → route to ALL lead roles
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.audit import AuditLog
from app.models.change import Change
from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

class WorkflowEngine:
    async def route_change(
        self,
        db: AsyncSession,
        change: Change,
        risk_result: dict[str, Any],
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Route a change based on its risk assessment. Creates approval records as needed."""
        risk_level = risk_result.get("risk_level", "medium")
        auto_approve = risk_result.get("auto_approve", False)
        timeout_at = datetime.now(UTC) + timedelta(hours=settings.approval_timeout_hours)

        if auto_approve and risk_level == "low":
            # Auto-approve: directly transition to Approved
            change.status = "Approved"
            await db.flush()
            await self._log_audit(db, change.id, user_id, "auto_approved", {
                "risk_score": risk_result.get("risk_score"),
                "reason": "Low risk — auto-approved by workflow engine",
            })
            return {"next_step": "auto-approve", "approvals_created": 0}

        # Determine which roles need to approve
        required_roles = self._determine_required_roles(change, risk_level)

        approvals_created = 0
        for role in required_roles:
            approval = Approval(
                change_id=change.id,
                role_required=role,
                status="Pending",
                timeout_at=timeout_at,
            )
            db.add(approval)
            approvals_created += 1

        change.status = "Pending"
        await db.flush()

        await self._log_audit(db, change.id, user_id, "routed_for_approval", {
            "risk_level": risk_level,
            "required_roles": required_roles,
            "timeout_at": timeout_at.isoformat(),
        })

        next_step = "cab-required" if risk_level == "high" else "targeted-approval"
        return {"next_step": next_step, "approvals_created": approvals_created, "required_roles": required_roles}

    def _determine_required_roles(self, change: Change, risk_level: str) -> list[str]:
        """Based on change type and risk level, decide who needs to approve."""

        if risk_level == "high":
            # CAB: everyone
            return ["Network", "Security", "DC Manager"]

        # Medium: targeted
        roles: list[str] = []
        change_type = change.change_type.lower() if change.change_type else ""

        if change_type in ("firewall",):
            roles.append("Security")
        if change_type in ("switch", "vlan", "port"):
            roles.append("Network")
        if change_type in ("rack",):
            roles.append("DC Manager")
        if change_type in ("cloudsg",):
            roles.append("Security")
            roles.append("Network")

        if not roles:
            roles.append("Network")

        return roles

    async def check_approvals(self, db: AsyncSession, change_id: str) -> dict[str, Any]:
        """Check if all required approvals for a change have been granted."""
        result = await db.execute(
            select(Approval).where(Approval.change_id == change_id)
        )
        approvals = list(result.scalars().all())

        if not approvals:
            return {"all_approved": True, "pending": 0, "approved": 0, "rejected": 0}

        pending = sum(1 for a in approvals if a.status == "Pending")
        approved = sum(1 for a in approvals if a.status == "Approved")
        rejected = sum(1 for a in approvals if a.status == "Rejected")

        all_approved = pending == 0 and rejected == 0 and approved > 0
        any_rejected = rejected > 0

        return {
            "all_approved": all_approved,
            "any_rejected": any_rejected,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "total": len(approvals),
        }

    async def handle_timeout(self, db: AsyncSession, change_id: str) -> int:
        """Check for timed-out approvals and escalate. Returns count of timed-out approvals."""
        now = datetime.now(UTC)
        result = await db.execute(
            select(Approval).where(
                Approval.change_id == change_id,
                Approval.status == "Pending",
                Approval.timeout_at <= now,
            )
        )
        timed_out = list(result.scalars().all())
        for approval in timed_out:
            approval.status = "Rejected"
            approval.comment = "Auto-rejected: approval timeout exceeded"
            approval.decided_at = now

        if timed_out:
            await self._log_audit(db, change_id, None, "approval_timeout", {
                "timed_out_count": len(timed_out),
            })
            await db.flush()

        return len(timed_out)

    async def _log_audit(
        self,
        db: AsyncSession,
        change_id: str,
        user_id: int | None,
        action: str,
        details: dict[str, Any] | None = None,
    ):
        log = AuditLog(
            change_id=change_id,
            user_id=user_id,
            action=action,
            details=details,
        )
        db.add(log)
        await db.flush()


workflow_engine = WorkflowEngine()
