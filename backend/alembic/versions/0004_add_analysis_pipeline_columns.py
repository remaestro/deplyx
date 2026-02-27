"""add analysis pipeline columns to changes

Revision ID: 0004_add_analysis_pipeline_columns
Revises: 0003_add_impact_cache
Create Date: 2026-02-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_analysis_pipeline_columns"
down_revision: Union[str, None] = "0003_add_impact_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.add_column(
        "changes",
        sa.Column("analysis_stage", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "changes",
        sa.Column("analysis_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "changes",
        sa.Column("analysis_last_error", sa.Text(), nullable=True),
    )



def downgrade() -> None:
    op.drop_column("changes", "analysis_last_error")
    op.drop_column("changes", "analysis_attempts")
    op.drop_column("changes", "analysis_stage")
