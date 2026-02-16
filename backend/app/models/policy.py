from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Policy(TimestampMixin, Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)  # time_restriction | double_validation | auto_block
    condition: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[str] = mapped_column(String(64), default="block")  # block | warn | require_double_approval
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
