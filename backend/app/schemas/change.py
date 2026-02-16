from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ChangeTypeEnum(StrEnum):
    FIREWALL = "Firewall"
    SWITCH = "Switch"
    VLAN = "VLAN"
    PORT = "Port"
    RACK = "Rack"
    CLOUD_SG = "CloudSG"


class ChangeActionEnum(StrEnum):
    # Firewall actions
    ADD_RULE = "add_rule"
    REMOVE_RULE = "remove_rule"
    MODIFY_RULE = "modify_rule"
    DISABLE_RULE = "disable_rule"
    # Switch / Port actions
    CHANGE_VLAN = "change_vlan"
    DISABLE_PORT = "disable_port"
    ENABLE_PORT = "enable_port"
    SHUTDOWN_INTERFACE = "shutdown_interface"
    # Device-level actions
    REBOOT_DEVICE = "reboot_device"
    DECOMMISSION = "decommission"
    FIRMWARE_UPGRADE = "firmware_upgrade"
    CONFIG_CHANGE = "config_change"
    # VLAN actions
    DELETE_VLAN = "delete_vlan"
    MODIFY_VLAN = "modify_vlan"
    # Cloud actions
    MODIFY_SG = "modify_sg"
    DELETE_SG = "delete_sg"


class EnvironmentEnum(StrEnum):
    PROD = "Prod"
    PREPROD = "Preprod"
    DC1 = "DC1"
    DC2 = "DC2"


class ChangeStatusEnum(StrEnum):
    DRAFT = "Draft"
    PENDING = "Pending"
    ANALYZING = "Analyzing"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    EXECUTING = "Executing"
    COMPLETED = "Completed"
    ROLLED_BACK = "RolledBack"


class ChangeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    change_type: ChangeTypeEnum
    environment: EnvironmentEnum
    action: ChangeActionEnum = Field(..., description="Specific action being performed, e.g. remove_rule, disable_port")
    description: str = Field(..., min_length=1)
    execution_plan: str = Field(..., min_length=1)
    rollback_plan: str = Field(..., min_length=1)
    maintenance_window_start: datetime
    maintenance_window_end: datetime
    target_components: list[str] = Field(default_factory=list, description="List of graph node IDs that this change targets")

    @model_validator(mode="after")
    def validate_maintenance_window(self):
        if self.maintenance_window_end <= self.maintenance_window_start:
            raise ValueError("maintenance_window_end must be after maintenance_window_start")
        return self


class ChangeUpdate(BaseModel):
    title: str | None = None
    action: ChangeActionEnum | None = None
    description: str | None = None
    execution_plan: str | None = None
    rollback_plan: str | None = None
    maintenance_window_start: datetime | None = None
    maintenance_window_end: datetime | None = None
    target_components: list[str] | None = None


class ImpactedComponentRead(BaseModel):
    graph_node_id: str
    component_type: str
    impact_level: str

    model_config = {"from_attributes": True}


class ChangeRead(BaseModel):
    id: str
    title: str
    change_type: str
    environment: str
    action: str | None
    description: str
    execution_plan: str
    rollback_plan: str | None
    maintenance_window_start: datetime | None
    maintenance_window_end: datetime | None
    status: str
    risk_score: float | None
    risk_level: str | None
    created_by: int
    reject_reason: str | None
    created_at: datetime
    updated_at: datetime
    impacted_components: list[ImpactedComponentRead] = []

    model_config = {"from_attributes": True}


class ChangeListItem(BaseModel):
    id: str
    title: str
    change_type: str
    environment: str
    status: str
    risk_score: float | None
    risk_level: str | None
    created_by: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RejectRequest(BaseModel):
    reason: str = ""
