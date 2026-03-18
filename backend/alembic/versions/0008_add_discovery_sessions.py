"""add discovery sessions and results

Revision ID: 0008_add_discovery_sessions
Revises: 0007_add_last_sync_detail
Create Date: 2026-03-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_add_discovery_sessions"
down_revision: Union[str, None] = "0007_add_last_sync_detail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discovery_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("ports", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "discovery_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("name_hint", sa.String(length=255), nullable=True),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("selected_connector_type", sa.String(length=64), nullable=True),
        sa.Column("suggested_connector_types", sa.JSON(), nullable=False),
        sa.Column("probe_detail", sa.JSON(), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("classification_reasons", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["discovery_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovery_results_session_id", "discovery_results", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_discovery_results_session_id", table_name="discovery_results")
    op.drop_table("discovery_results")
    op.drop_table("discovery_sessions")