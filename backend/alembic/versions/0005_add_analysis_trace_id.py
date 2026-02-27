"""add analysis trace id to changes

Revision ID: 0005_add_analysis_trace_id
Revises: 0004_add_analysis_pipeline_columns
Create Date: 2026-02-24 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_add_analysis_trace_id"
down_revision: Union[str, None] = "0004_add_analysis_pipeline_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.add_column("changes", sa.Column("analysis_trace_id", sa.String(length=36), nullable=True))



def downgrade() -> None:
    op.drop_column("changes", "analysis_trace_id")
