"""add project material bindings

Revision ID: d129e4f6a7b8
Revises: d127c4d5e6f7
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "d129e4f6a7b8"
down_revision = "d127c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_material_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["learning_projects.id"]),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_material_bindings_id",
        "project_material_bindings",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_project_material_bindings_project_id",
        "project_material_bindings",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_material_bindings_material_id",
        "project_material_bindings",
        ["material_id"],
        unique=False,
    )
    op.create_index(
        "uq_project_material_bindings_active",
        "project_material_bindings",
        ["project_id", "material_id"],
        unique=True,
        postgresql_where=sa.text("unbound_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_project_material_bindings_active",
        table_name="project_material_bindings",
    )
    op.drop_index(
        "ix_project_material_bindings_material_id",
        table_name="project_material_bindings",
    )
    op.drop_index(
        "ix_project_material_bindings_project_id",
        table_name="project_material_bindings",
    )
    op.drop_index(
        "ix_project_material_bindings_id",
        table_name="project_material_bindings",
    )
    op.drop_table("project_material_bindings")
