from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import Role, require_role
from app.core.security import get_current_user
from app.models.approval import Approval
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.workflow import ApprovalDecision, ApprovalRead, AuditLogRead
from app.workflow.engine import workflow_engine

router = APIRouter(tags=["workflow"])


# ── Approvals ──────────────────────────────────────────────────────────


@router.get("/changes/{change_id}/approvals", response_model=list[ApprovalRead])
async def list_approvals(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(Approval).where(Approval.change_id == change_id))
    return list(result.scalars().all())


@router.post("/changes/{change_id}/approvals/{approval_id}", response_model=ApprovalRead)
async def submit_approval_decision(
    change_id: str,
    approval_id: int,
    body: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN, Role.APPROVER, Role.NETWORK, Role.SECURITY, Role.DC_MANAGER)),
):
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id, Approval.change_id == change_id)
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "Pending":
        raise HTTPException(status_code=400, detail="Approval already decided")

    # Verify user's role matches the required role
    if current_user.role != Role.ADMIN.value and current_user.role != approval.role_required:
        raise HTTPException(status_code=403, detail=f"Role '{current_user.role}' cannot fulfill '{approval.role_required}' approval")

    if body.status not in ("Approved", "Rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'Approved' or 'Rejected'")

    approval.status = body.status
    approval.comment = body.comment
    approval.approver_id = current_user.id
    approval.decided_at = datetime.now(UTC)
    await db.flush()

    # Log audit
    audit = AuditLog(
        change_id=change_id,
        user_id=current_user.id,
        action=f"approval_{body.status.lower()}",
        details={"approval_id": approval_id, "comment": body.comment, "role": approval.role_required},
    )
    db.add(audit)
    await db.flush()

    # Check if all approvals are done → auto-transition change status
    check = await workflow_engine.check_approvals(db, change_id)
    if check["all_approved"]:
        from app.services.change_service import transition_status
        await transition_status(db, change_id, "Approved")
        audit2 = AuditLog(
            change_id=change_id, user_id=current_user.id,
            action="change_approved", details={"approved_by_workflow": True},
        )
        db.add(audit2)
        await db.flush()
    elif check.get("any_rejected"):
        from app.services.change_service import transition_status
        await transition_status(db, change_id, "Rejected", reject_reason="Rejected by approver")

    return approval


@router.get("/changes/{change_id}/approval-status")
async def get_approval_status(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await workflow_engine.check_approvals(db, change_id)


# ── Audit Log ──────────────────────────────────────────────────────────


@router.get("/audit-log", response_model=list[AuditLogRead])
async def list_audit_logs(
    change_id: str | None = Query(None),
    user_id: int | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    if change_id:
        stmt = stmt.where(AuditLog.change_id == change_id)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/changes/{change_id}/audit-log", response_model=list[AuditLogRead])
async def get_change_audit_log(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(AuditLog).where(AuditLog.change_id == change_id).order_by(AuditLog.timestamp.desc())
    )
    return list(result.scalars().all())
