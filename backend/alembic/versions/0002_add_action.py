"""add action column to changes

Revision ID: 0002_add_action
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_add_action'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('changes', sa.Column('action', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('changes', 'action')
