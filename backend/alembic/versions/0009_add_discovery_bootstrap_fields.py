"""add discovery bootstrap fields

Revision ID: 0009_disc_bootstrap
Revises: 0008_add_discovery_sessions
Create Date: 2026-03-18 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_disc_bootstrap"
down_revision: Union[str, None] = "0008_add_discovery_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("discovery_results", sa.Column("preflight_status", sa.String(length=16), nullable=False, server_default="pending"))
    op.add_column("discovery_results", sa.Column("bootstrap_status", sa.String(length=16), nullable=False, server_default="pending"))
    op.add_column("discovery_results", sa.Column("connector_id", sa.Integer(), nullable=True))
    op.add_column("discovery_results", sa.Column("connector_name", sa.String(length=255), nullable=True))
    op.add_column("discovery_results", sa.Column("bootstrap_detail", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("discovery_results", "bootstrap_detail")
    op.drop_column("discovery_results", "connector_name")
    op.drop_column("discovery_results", "connector_id")
    op.drop_column("discovery_results", "bootstrap_status")
    op.drop_column("discovery_results", "preflight_status")