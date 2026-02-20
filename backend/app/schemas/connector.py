from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Literal


class ConnectorCreate(BaseModel):
    name: str
    connector_type: str  # paloalto | fortinet | cisco | checkpoint | juniper
    config: dict = {}
    sync_mode: str = "on-demand"  # pull | webhook | on-demand
    sync_interval_minutes: int = 60


class ConnectorUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    sync_mode: str | None = None
    sync_interval_minutes: int | None = None


class ConnectorRead(BaseModel):
    id: int
    name: str
    connector_type: str
    config: dict
    sync_mode: str
    sync_interval_minutes: int
    last_sync_at: datetime | None
    status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectorOperationRequest(BaseModel):
    contract_version: str = "2.0"
    operation: Literal["sync", "validate", "simulate", "apply", "custom"]
    action: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)


class ConnectorOperationError(BaseModel):
    code: str = "connector_error"
    message: str
    retryable: bool = False
    field: str | None = None


class ConnectorOperationResult(BaseModel):
    contract_version: str = "2.0"
    operation: str
    connector_type: str
    ok: bool
    status: Literal["success", "failed", "partial", "accepted"]
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    errors: list[ConnectorOperationError] = Field(default_factory=list)
