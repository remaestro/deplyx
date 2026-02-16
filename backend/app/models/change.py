import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ChangeType(str):
    FIREWALL = "Firewall"
    SWITCH = "Switch"
    VLAN = "VLAN"
    PORT = "Port"
    RACK = "Rack"
    CLOUD_SG = "CloudSG"


class Environment(str):
    PROD = "Prod"
    PREPROD = "Preprod"
    DC1 = "DC1"
    DC2 = "DC2"


class ChangeStatus(str):
    DRAFT = "Draft"
    PENDING = "Pending"
    ANALYZING = "Analyzing"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    EXECUTING = "Executing"
    COMPLETED = "Completed"
    ROLLED_BACK = "RolledBack"


def _uuid() -> str:
    return str(uuid.uuid4())


class Change(TimestampMixin, Base):
    __tablename__ = "changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    execution_plan: Mapped[str] = mapped_column(Text, default="")
    rollback_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    maintenance_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    maintenance_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ChangeStatus.DRAFT)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    impact_cache: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    impacted_components: Mapped[list["ChangeImpactedComponent"]] = relationship(
        back_populates="change", cascade="all, delete-orphan"
    )


class ChangeImpactedComponent(Base):
    __tablename__ = "change_impacted_components"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    change_id: Mapped[str] = mapped_column(String(36), ForeignKey("changes.id", ondelete="CASCADE"), nullable=False)
    graph_node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    component_type: Mapped[str] = mapped_column(String(64), default="")
    impact_level: Mapped[str] = mapped_column(String(16), default="direct")  # direct | indirect

    change: Mapped["Change"] = relationship(back_populates="impacted_components")
