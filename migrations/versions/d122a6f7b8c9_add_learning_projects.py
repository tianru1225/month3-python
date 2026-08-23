"""add learning projects

Revision ID: d122a6f7b8c9
Revises: 7c1a8796e34b
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "d122a6f7b8c9"
down_revision = "7c1a8796e34b"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("current_level", sa.String(length=40), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column(
            "daily_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
        sa.Column(
            "weekly_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("7"),
        ),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','ACTIVE','PAUSED','COMPLETED','ARCHIVED')",
            name="ck_learning_projects_status",
        ),
        sa.CheckConstraint(
            "daily_minutes BETWEEN 1 AND 1440",
            name="ck_learning_projects_daily_minutes",
        ),
        sa.CheckConstraint(
            "weekly_days BETWEEN 1 AND 7",
            name="ck_learning_projects_weekly_days",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_learning_projects_id",
        "learning_projects",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_learning_projects_user_id",
        "learning_projects",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_learning_projects_user_id", table_name="learning_projects")
    op.drop_index("ix_learning_projects_id", table_name="learning_projects")
    op.drop_table("learning_projects")
