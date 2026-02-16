from pydantic import BaseModel
from datetime import datetime


class ApprovalRead(BaseModel):
    id: int
    change_id: str
    approver_id: int | None
    role_required: str
    status: str
    comment: str | None
    decided_at: datetime | None
    timeout_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    status: str  # "Approved" or "Rejected"
    comment: str = ""


class AuditLogRead(BaseModel):
    id: int
    change_id: str | None
    user_id: int | None
    action: str
    details: dict | None
    timestamp: datetime

    model_config = {"from_attributes": True}
