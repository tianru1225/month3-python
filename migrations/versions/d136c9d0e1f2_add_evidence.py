"""add immutable task evidence"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision = "d136c9d0e1f2"
down_revision = "d134b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_version_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(length=20), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("source_ref", sa.String(length=500), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("test_report", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name="ck_evidence_attempt_number",
        ),
        sa.CheckConstraint(
            "evidence_type IN ('TEXT_ANSWER','TEST_REPORT')",
            name="ck_evidence_type",
        ),
        sa.CheckConstraint(
            "source_kind IN ('USER','AUTOMATION')",
            name="ck_evidence_source_kind",
        ),
        sa.CheckConstraint(
            "(evidence_type = 'TEXT_ANSWER' "
            "AND text_content IS NOT NULL AND test_report IS NULL) OR "
            "(evidence_type = 'TEST_REPORT' "
            "AND text_content IS NULL AND test_report IS NOT NULL)",
            name="ck_evidence_payload",
        ),
        sa.CheckConstraint(
            "text_content IS NULL OR length(trim(text_content)) BETWEEN 1 AND 20000",
            name="ck_evidence_text_content",
        ),
        sa.CheckConstraint(
            "(source_kind = 'USER' AND source_ref IS NULL) OR "
            "(source_kind = 'AUTOMATION' AND source_ref IS NOT NULL "
            "AND length(trim(source_ref)) BETWEEN 1 AND 500)",
            name="ck_evidence_source_ref",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "plan_version_id"],
            ["learning_tasks.id", "learning_tasks.plan_version_id"],
            name="fk_evidence_task_version",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "attempt_number",
            name="uq_evidence_task_attempt",
        ),
    )
    op.create_index("ix_evidence_id", "evidence", ["id"], unique=False)
    op.create_index(
        "ix_evidence_plan_version_id",
        "evidence",
        ["plan_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_task_id",
        "evidence",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_submitted_by_user_id",
        "evidence",
        ["submitted_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_task_submitted",
        "evidence",
        ["task_id", "submitted_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_task_submitted", table_name="evidence")
    op.drop_index("ix_evidence_submitted_by_user_id", table_name="evidence")
    op.drop_index("ix_evidence_task_id", table_name="evidence")
    op.drop_index("ix_evidence_plan_version_id", table_name="evidence")
    op.drop_index("ix_evidence_id", table_name="evidence")
    op.drop_table("evidence")
