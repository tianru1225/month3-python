"""add learning plans and immutable plan versions"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision = "d133a7b8c9d0"
down_revision = "d132f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 160",
            name="ck_learning_plans_name",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["learning_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_plans_id", "learning_plans", ["id"], unique=False)
    op.create_index(
        "ix_learning_plans_project_id",
        "learning_plans",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "plan_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=True),
        sa.Column("model_name", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "version_number >= 1", name="ck_plan_versions_version_number"
        ),
        sa.CheckConstraint(
            "length(trim(goal)) BETWEEN 1 AND 5000",
            name="ck_plan_versions_goal",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','REJECTED')",
            name="ck_plan_versions_status",
        ),
        sa.CheckConstraint(
            "source_kind IN ('MANUAL','TEMPLATE','MODEL')",
            name="ck_plan_versions_source_kind",
        ),
        sa.CheckConstraint(
            "provider_name IS NULL OR length(trim(provider_name)) BETWEEN 1 AND 80",
            name="ck_plan_versions_provider_name",
        ),
        sa.CheckConstraint(
            "model_name IS NULL OR length(trim(model_name)) BETWEEN 1 AND 160",
            name="ck_plan_versions_model_name",
        ),
        sa.CheckConstraint(
            "(source_kind = 'MODEL' AND provider_name IS NOT NULL "
            "AND model_name IS NOT NULL) OR "
            "(source_kind <> 'MODEL' AND provider_name IS NULL "
            "AND model_name IS NULL)",
            name="ck_plan_versions_model_identity",
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND is_current = false "
            "AND published_at IS NULL AND confirmed_by_user_id IS NULL "
            "AND rejection_reason IS NULL) OR "
            "(status = 'PUBLISHED' AND published_at IS NOT NULL "
            "AND confirmed_by_user_id IS NOT NULL "
            "AND rejection_reason IS NULL) OR "
            "(status = 'REJECTED' AND is_current = false "
            "AND published_at IS NULL AND confirmed_by_user_id IS NULL "
            "AND rejection_reason IS NOT NULL "
            "AND length(trim(rejection_reason)) BETWEEN 1 AND 2000)",
            name="ck_plan_versions_state_fields",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["learning_plans.id"]),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id", "version_number", name="uq_plan_versions_number"
        ),
    )
    op.create_index("ix_plan_versions_id", "plan_versions", ["id"], unique=False)
    op.create_index(
        "ix_plan_versions_plan_id", "plan_versions", ["plan_id"], unique=False
    )
    op.create_index(
        "ix_plan_versions_status", "plan_versions", ["status"], unique=False
    )
    op.create_index(
        "uq_plan_versions_current",
        "plan_versions",
        ["plan_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
        sqlite_where=sa.text("is_current = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_plan_versions_current", table_name="plan_versions")
    op.drop_index("ix_plan_versions_status", table_name="plan_versions")
    op.drop_index("ix_plan_versions_plan_id", table_name="plan_versions")
    op.drop_index("ix_plan_versions_id", table_name="plan_versions")
    op.drop_table("plan_versions")
    op.drop_index("ix_learning_plans_project_id", table_name="learning_plans")
    op.drop_index("ix_learning_plans_id", table_name="learning_plans")
    op.drop_table("learning_plans")
