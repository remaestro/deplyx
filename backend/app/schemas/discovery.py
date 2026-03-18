from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DiscoveryInventoryDeviceInput(BaseModel):
    host: str
    name: str | None = None
    connector_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscoverySessionCreate(BaseModel):
    name: str | None = None
    targets: list[str] = Field(default_factory=list)
    cidrs: list[str] = Field(default_factory=list)
    inventory: list[DiscoveryInventoryDeviceInput] = Field(default_factory=list)
    ports: list[int] = Field(default_factory=lambda: [22, 80, 161, 389, 443, 636, 3000, 5432, 6379, 8080, 8443, 9090, 9200])
    timeout_seconds: int = 3
    max_targets: int = 128

    @model_validator(mode="after")
    def validate_input(self) -> "DiscoverySessionCreate":
        if not self.targets and not self.cidrs and not self.inventory:
            raise ValueError("At least one of targets, cidrs, or inventory must be provided")
        return self


class DiscoveryResultRead(BaseModel):
    id: int
    session_id: int
    host: str
    name_hint: str | None
    source_kind: str
    status: str
    selected_connector_type: str | None
    suggested_connector_types: list[str] = Field(default_factory=list)
    preflight_status: str
    bootstrap_status: str
    connector_id: int | None
    connector_name: str | None
    probe_detail: dict[str, Any] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)
    classification_reasons: list[str] = Field(default_factory=list)
    bootstrap_detail: dict[str, Any] | None = None
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscoverySessionRead(BaseModel):
    id: int
    name: str | None
    status: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    ports: list[int] = Field(default_factory=list)
    timeout_seconds: int
    target_count: int
    summary: dict[str, Any] | None = None
    started_at: datetime | None
    completed_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscoverySessionDetail(DiscoverySessionRead):
    results: list[DiscoveryResultRead] = Field(default_factory=list)


class DiscoveryBootstrapSelection(BaseModel):
    result_id: int
    connector_type: str | None = None
    run_sync: bool | None = None


class DiscoveryBootstrapRequest(BaseModel):
    connector_defaults: dict[str, dict[str, Any]] = Field(default_factory=dict)
    default_config: dict[str, Any] = Field(default_factory=dict)
    sync_mode: str = "on-demand"
    sync_interval_minutes: int = 60
    run_sync: bool = True
    allow_ambiguous: bool = False
    on_existing: str = "skip"
    items: list[DiscoveryBootstrapSelection] = Field(default_factory=list)


class DiscoveryBootstrapItem(BaseModel):
    result_id: int
    host: str
    connector_type: str | None = None
    connector_id: int | None = None
    connector_name: str | None = None
    preflight_status: str
    bootstrap_status: str
    detail: dict[str, Any] = Field(default_factory=dict)


class DiscoveryBootstrapResponse(BaseModel):
    session_id: int
    processed: int
    created: int
    synced: int
    skipped: int
    errors: int
    items: list[DiscoveryBootstrapItem] = Field(default_factory=list)