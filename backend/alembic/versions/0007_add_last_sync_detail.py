"""add last_sync_detail jsonb to connectors

Revision ID: 0007_add_last_sync_detail
Revises: 0006_seed_workflow_thresholds
Create Date: 2026-03-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


revision: str = "0007_add_last_sync_detail"
down_revision: Union[str, None] = "0006_seed_workflow_thresholds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("connectors", sa.Column("last_sync_detail", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("connectors", "last_sync_detail")
