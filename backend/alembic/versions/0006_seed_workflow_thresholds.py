"""seed workflow thresholds policy

Revision ID: 0006_seed_workflow_thresholds
Revises: 0005_add_analysis_trace_id
Create Date: 2026-02-24 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0006_seed_workflow_thresholds"
down_revision: Union[str, None] = "0005_add_analysis_trace_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO policies (name, description, rule_type, condition, action, enabled, created_by)
        SELECT
            'Workflow Thresholds',
            'Seeded default workflow thresholds for pipeline routing',
            'workflow_thresholds',
            json_build_object(
                'auto_approve_max', 30,
                'targeted_max', 70,
                'cab_min', 71
            )::json,
            'warn',
            TRUE,
            NULL
        WHERE NOT EXISTS (
            SELECT 1
            FROM policies
            WHERE rule_type = 'workflow_thresholds' AND enabled = TRUE
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM policies
        WHERE name = 'Workflow Thresholds'
          AND description = 'Seeded default workflow thresholds for pipeline routing'
          AND rule_type = 'workflow_thresholds'
          AND action = 'warn'
          AND enabled = TRUE
          AND created_by IS NULL;
        """
    )
