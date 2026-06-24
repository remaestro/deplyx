"""add organizations and sites (multi-tenancy)

Revision ID: 0010_add_org_site
Revises: 0009_disc_bootstrap
Create Date: 2026-03-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_add_org_site"
down_revision: Union[str, None] = "0009_disc_bootstrap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_site_org_slug"),
    )
    op.create_index("ix_sites_organization_id", "sites", ["organization_id"])

    op.add_column("users", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_foreign_key("fk_users_organization_id", "users", "organizations", ["organization_id"], ["id"])

    op.add_column("connectors", sa.Column("site_id", sa.Integer(), nullable=True))
    op.create_index("ix_connectors_site_id", "connectors", ["site_id"])
    op.create_foreign_key("fk_connectors_site_id", "connectors", "sites", ["site_id"], ["id"])

    op.add_column("changes", sa.Column("site_id", sa.Integer(), nullable=True))
    op.create_index("ix_changes_site_id", "changes", ["site_id"])
    op.create_foreign_key("fk_changes_site_id", "changes", "sites", ["site_id"], ["id"])

    # ── Seed default Organization + Site and backfill existing data ──────
    conn = op.get_bind()
    org_id = conn.execute(
        sa.text(
            "INSERT INTO organizations (name, slug) VALUES (:name, :slug) RETURNING id"
        ),
        {"name": "Improtech Lab", "slug": "improtech-lab"},
    ).scalar_one()

    site_id = conn.execute(
        sa.text(
            "INSERT INTO sites (organization_id, name, slug, location) "
            "VALUES (:org, :name, :slug, :loc) RETURNING id"
        ),
        {"org": org_id, "name": "Lab Principal", "slug": "lab-principal", "loc": "192.168.170.0/24"},
    ).scalar_one()

    conn.execute(sa.text("UPDATE users SET organization_id = :org WHERE organization_id IS NULL"), {"org": org_id})
    conn.execute(sa.text("UPDATE connectors SET site_id = :site WHERE site_id IS NULL"), {"site": site_id})
    conn.execute(sa.text("UPDATE changes SET site_id = :site WHERE site_id IS NULL"), {"site": site_id})


def downgrade() -> None:
    op.drop_constraint("fk_changes_site_id", "changes", type_="foreignkey")
    op.drop_index("ix_changes_site_id", table_name="changes")
    op.drop_column("changes", "site_id")

    op.drop_constraint("fk_connectors_site_id", "connectors", type_="foreignkey")
    op.drop_index("ix_connectors_site_id", table_name="connectors")
    op.drop_column("connectors", "site_id")

    op.drop_constraint("fk_users_organization_id", "users", type_="foreignkey")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_column("users", "organization_id")

    op.drop_index("ix_sites_organization_id", table_name="sites")
    op.drop_table("sites")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
