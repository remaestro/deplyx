from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class PolicyRuleType(str, Enum):
    TIME_RESTRICTION = "time_restriction"
    DOUBLE_VALIDATION = "double_validation"
    AUTO_BLOCK = "auto_block"


class PolicyAction(str, Enum):
    BLOCK = "block"
    WARN = "warn"
    REQUIRE_DOUBLE_APPROVAL = "require_double_approval"


class PolicyCreate(BaseModel):
    name: str
    description: str = ""
    rule_type: PolicyRuleType
    condition: dict = {}
    action: PolicyAction = PolicyAction.BLOCK
    enabled: bool = True


class PolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    condition: dict | None = None
    action: PolicyAction | None = None
    enabled: bool | None = None


class PolicyRead(BaseModel):
    id: int
    name: str
    description: str
    rule_type: PolicyRuleType
    condition: dict
    action: PolicyAction
    enabled: bool
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PolicyEvaluationResult(BaseModel):
    policy_id: int
    policy_name: str
    rule_type: str
    triggered: bool
    action: str
    reason: str | None = None


class PolicyEvaluationResponse(BaseModel):
    change_id: str
    results: list[PolicyEvaluationResult]
    blocked: bool
    warnings: list[str]
