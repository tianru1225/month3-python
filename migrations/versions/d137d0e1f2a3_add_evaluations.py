"""add evaluation records"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision = "d137d0e1f2a3"
down_revision = "d136c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("rule_status", sa.String(length=20), nullable=False),
        sa.Column(
            "rule_result",
            sa.JSON(none_as_null=True),
            nullable=False,
        ),
        sa.Column("model_suggestion", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("human_decision", sa.String(length=30), nullable=True),
        sa.Column("human_note", sa.Text(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_decision", sa.String(length=30), nullable=True),
        sa.Column("finalized_by_user_id", sa.Integer(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "rule_status IN ('PASS','FAIL','INCONCLUSIVE')",
            name="ck_evaluations_rule_status",
        ),
        sa.CheckConstraint(
            "human_decision IS NULL OR human_decision IN "
            "('PASSED','REVISION_REQUIRED')",
            name="ck_evaluations_human_decision",
        ),
        sa.CheckConstraint(
            "final_decision IS NULL OR final_decision IN "
            "('PASSED','REVISION_REQUIRED')",
            name="ck_evaluations_final_decision",
        ),
        sa.CheckConstraint(
            "(human_decision IS NULL AND human_note IS NULL "
            "AND confirmed_by_user_id IS NULL AND confirmed_at IS NULL) OR "
            "(human_decision IS NOT NULL AND human_note IS NOT NULL "
            "AND confirmed_by_user_id IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_evaluations_human_fields",
        ),
        sa.CheckConstraint(
            "(final_decision IS NULL AND finalized_by_user_id IS NULL "
            "AND finalized_at IS NULL) OR "
            "(final_decision IS NOT NULL AND finalized_by_user_id IS NOT NULL "
            "AND finalized_at IS NOT NULL)",
            name="ck_evaluations_final_fields",
        ),
        sa.CheckConstraint(
            "final_decision IS NULL OR final_decision = human_decision",
            name="ck_evaluations_final_matches_human",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            name="fk_evaluations_evidence_id",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["users.id"],
            name="fk_evaluations_confirmed_by_user_id",
        ),
        sa.ForeignKeyConstraint(
            ["finalized_by_user_id"],
            ["users.id"],
            name="fk_evaluations_finalized_by_user_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_id",
            name="uq_evaluations_evidence_id",
        ),
    )
    op.create_index("ix_evaluations_id", "evaluations", ["id"], unique=False)
    op.create_index(
        "ix_evaluations_evidence_id",
        "evaluations",
        ["evidence_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluations_confirmed_by_user_id",
        "evaluations",
        ["confirmed_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluations_finalized_by_user_id",
        "evaluations",
        ["finalized_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluations_finalized_by_user_id",
        table_name="evaluations",
    )
    op.drop_index(
        "ix_evaluations_confirmed_by_user_id",
        table_name="evaluations",
    )
    op.drop_index(
        "ix_evaluations_evidence_id",
        table_name="evaluations",
    )
    op.drop_index("ix_evaluations_id", table_name="evaluations")
    op.drop_table("evaluations")
