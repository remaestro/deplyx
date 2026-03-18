from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class DiscoverySession(TimestampMixin, Base):
    __tablename__ = "discovery_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    ports: Mapped[list[int]] = mapped_column(JSON, default=list)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3)
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    results: Mapped[list["DiscoveryResult"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="DiscoveryResult.id",
    )


class DiscoveryResult(TimestampMixin, Base):
    __tablename__ = "discovery_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    name_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(32), default="target")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    selected_connector_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suggested_connector_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    preflight_status: Mapped[str] = mapped_column(String(16), default="pending")
    bootstrap_status: Mapped[str] = mapped_column(String(16), default="pending")
    connector_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connector_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    probe_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    classification_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    bootstrap_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[DiscoverySession] = relationship(back_populates="results")