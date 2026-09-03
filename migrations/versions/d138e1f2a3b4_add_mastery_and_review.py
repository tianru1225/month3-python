"""add mastery records and review items

Revision ID: d138e1f2a3b4
Revises: d137d0e1f2a3
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d138e1f2a3b4"
down_revision: str | None = "d137d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mastery_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_node_id", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("score_before", sa.Integer(), nullable=False),
        sa.Column("score_after", sa.Integer(), nullable=False),
        sa.Column("level_after", sa.String(length=20), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("calculation", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "score_before BETWEEN 0 AND 100",
            name="ck_mastery_records_score_before",
        ),
        sa.CheckConstraint(
            "score_after BETWEEN 0 AND 100",
            name="ck_mastery_records_score_after",
        ),
        sa.CheckConstraint(
            "level_after IN ('NOVICE','DEVELOPING','PROFICIENT','MASTERED')",
            name="ck_mastery_records_level_after",
        ),
        sa.CheckConstraint(
            "decision IN ('PASSED','REVISION_REQUIRED')",
            name="ck_mastery_records_decision",
        ),
        sa.CheckConstraint(
            "interval_days BETWEEN 1 AND 3650",
            name="ck_mastery_records_interval_days",
        ),
        sa.CheckConstraint(
            "length(trim(algorithm_version)) BETWEEN 1 AND 80",
            name="ck_mastery_records_algorithm_version",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) BETWEEN 1 AND 5000",
            name="ck_mastery_records_reason",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
            name="fk_mastery_records_evaluation_id",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_node_id"],
            ["knowledge_nodes.id"],
            name="fk_mastery_records_knowledge_node_id",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["learning_projects.id"],
            name="fk_mastery_records_project_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_id",
            name="uq_mastery_records_evaluation_id",
        ),
    )
    op.create_index(
        "ix_mastery_records_id",
        "mastery_records",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_mastery_records_project_id",
        "mastery_records",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_mastery_records_knowledge_node_id",
        "mastery_records",
        ["knowledge_node_id"],
        unique=False,
    )
    op.create_index(
        "ix_mastery_records_evaluation_id",
        "mastery_records",
        ["evaluation_id"],
        unique=False,
    )
    op.create_index(
        "ix_mastery_records_project_node_recorded",
        "mastery_records",
        ["project_id", "knowledge_node_id", "recorded_at", "id"],
        unique=False,
    )

    op.create_table(
        "review_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_node_id", sa.Integer(), nullable=False),
        sa.Column("last_record_id", sa.Integer(), nullable=False),
        sa.Column("mastery_score", sa.Integer(), nullable=False),
        sa.Column("mastery_level", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mastery_score BETWEEN 0 AND 100",
            name="ck_review_items_mastery_score",
        ),
        sa.CheckConstraint(
            "mastery_level IN ('NOVICE','DEVELOPING','PROFICIENT','MASTERED')",
            name="ck_review_items_mastery_level",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','COMPLETED')",
            name="ck_review_items_status",
        ),
        sa.CheckConstraint(
            "interval_days BETWEEN 1 AND 3650",
            name="ck_review_items_interval_days",
        ),
        sa.CheckConstraint(
            "review_count >= 0",
            name="ck_review_items_review_count",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND completed_at IS NULL) OR "
            "(status = 'COMPLETED' AND completed_at IS NOT NULL "
            "AND last_reviewed_at IS NOT NULL)",
            name="ck_review_items_completion_fields",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_node_id"],
            ["knowledge_nodes.id"],
            name="fk_review_items_knowledge_node_id",
        ),
        sa.ForeignKeyConstraint(
            ["last_record_id"],
            ["mastery_records.id"],
            name="fk_review_items_last_record_id",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["learning_projects.id"],
            name="fk_review_items_project_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "last_record_id",
            name="uq_review_items_last_record_id",
        ),
        sa.UniqueConstraint(
            "project_id",
            "knowledge_node_id",
            name="uq_review_items_project_node",
        ),
    )
    op.create_index(
        "ix_review_items_id",
        "review_items",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_review_items_project_id",
        "review_items",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_items_knowledge_node_id",
        "review_items",
        ["knowledge_node_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_items_last_record_id",
        "review_items",
        ["last_record_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_items_project_due",
        "review_items",
        ["project_id", "status", "next_review_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("review_items")
    op.drop_table("mastery_records")
