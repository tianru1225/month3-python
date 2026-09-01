"""add learning tasks and same-version prerequisites"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision = "d134b8c9d0e1"
down_revision = "d133a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_version_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("deliverable", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "position >= 1",
            name="ck_learning_tasks_position",
        ),
        sa.CheckConstraint(
            "estimated_minutes BETWEEN 1 AND 1440",
            name="ck_learning_tasks_estimated_minutes",
        ),
        sa.CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 160",
            name="ck_learning_tasks_title",
        ),
        sa.CheckConstraint(
            "length(trim(objective)) BETWEEN 1 AND 5000",
            name="ck_learning_tasks_objective",
        ),
        sa.CheckConstraint(
            "length(trim(instructions)) BETWEEN 1 AND 10000",
            name="ck_learning_tasks_instructions",
        ),
        sa.CheckConstraint(
            "length(trim(deliverable)) BETWEEN 1 AND 5000",
            name="ck_learning_tasks_deliverable",
        ),
        sa.CheckConstraint(
            "status IN "
            "('DRAFT','READY','IN_PROGRESS','SUBMITTED','PASSED',"
            "'REVISION_REQUIRED')",
            name="ck_learning_tasks_status",
        ),
        sa.CheckConstraint(
            "(status = 'PASSED' AND completed_at IS NOT NULL) OR "
            "(status <> 'PASSED' AND completed_at IS NULL)",
            name="ck_learning_tasks_completed_at",
        ),
        sa.ForeignKeyConstraint(["plan_version_id"], ["plan_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "plan_version_id",
            name="uq_learning_tasks_id_plan_version",
        ),
        sa.UniqueConstraint(
            "plan_version_id",
            "position",
            name="uq_learning_tasks_version_position",
        ),
    )
    op.create_index("ix_learning_tasks_id", "learning_tasks", ["id"], unique=False)
    op.create_index(
        "ix_learning_tasks_plan_version_id",
        "learning_tasks",
        ["plan_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_learning_tasks_version_date_position",
        "learning_tasks",
        ["plan_version_id", "scheduled_date", "position"],
        unique=False,
    )

    op.create_table(
        "task_prerequisites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_version_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("prerequisite_task_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "task_id <> prerequisite_task_id",
            name="ck_task_prerequisites_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "plan_version_id"],
            ["learning_tasks.id", "learning_tasks.plan_version_id"],
            name="fk_task_prerequisites_task_version",
        ),
        sa.ForeignKeyConstraint(
            ["prerequisite_task_id", "plan_version_id"],
            ["learning_tasks.id", "learning_tasks.plan_version_id"],
            name="fk_task_prerequisites_prerequisite_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "prerequisite_task_id",
            name="uq_task_prerequisites_edge",
        ),
    )
    op.create_index(
        "ix_task_prerequisites_id",
        "task_prerequisites",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_task_prerequisites_plan_version_id",
        "task_prerequisites",
        ["plan_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_prerequisites_task_id",
        "task_prerequisites",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_prerequisites_prerequisite_task_id",
        "task_prerequisites",
        ["prerequisite_task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_prerequisites_prerequisite_task_id",
        table_name="task_prerequisites",
    )
    op.drop_index(
        "ix_task_prerequisites_task_id",
        table_name="task_prerequisites",
    )
    op.drop_index(
        "ix_task_prerequisites_plan_version_id",
        table_name="task_prerequisites",
    )
    op.drop_index(
        "ix_task_prerequisites_id",
        table_name="task_prerequisites",
    )
    op.drop_table("task_prerequisites")
    op.drop_index(
        "ix_learning_tasks_version_date_position",
        table_name="learning_tasks",
    )
    op.drop_index(
        "ix_learning_tasks_plan_version_id",
        table_name="learning_tasks",
    )
    op.drop_index("ix_learning_tasks_id", table_name="learning_tasks")
    op.drop_table("learning_tasks")
