from pydantic import BaseModel
from datetime import datetime


class ConnectorCreate(BaseModel):
    name: str
    connector_type: str  # paloalto | fortinet | cisco | aws | azure
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
