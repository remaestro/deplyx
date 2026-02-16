"""add impact_cache column to changes

Revision ID: 0003_add_impact_cache
Revises: 0002_add_action
Create Date: 2026-02-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003_add_impact_cache'
down_revision: Union[str, None] = '0002_add_action'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('changes', sa.Column('impact_cache', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('changes', 'impact_cache')
