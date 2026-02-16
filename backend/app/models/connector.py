from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Connector(TimestampMixin, Base):
    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False)  # paloalto | fortinet | cisco | aws | azure
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # host, credentials (should be encrypted in prod)
    sync_mode: Mapped[str] = mapped_column(String(16), default="on-demand")  # pull | webhook | on-demand
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="inactive")  # active | inactive | error
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
