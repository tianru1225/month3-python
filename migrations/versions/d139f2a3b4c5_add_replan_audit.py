"""add replan proposals and audit events

Revision ID: d139f2a3b4c5
Revises: d138e1f2a3b4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d139f2a3b4c5"
down_revision: str | None = "d138e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "replan_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("base_plan_version_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("trigger_code", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("proposed_content", sa.JSON(), nullable=False),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["learning_projects.id"]),
        sa.ForeignKeyConstraint(["base_plan_version_id"], ["plan_versions.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.CheckConstraint(
            "status IN ('PENDING','ACCEPTED','REJECTED')",
            name="ck_replan_proposals_status",
        ),
        sa.CheckConstraint(
            "length(trim(trigger_code)) BETWEEN 1 AND 80",
            name="ck_replan_proposals_trigger_code",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) BETWEEN 1 AND 5000",
            name="ck_replan_proposals_reason",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND decided_by_user_id IS NULL "
            "AND decided_at IS NULL AND decision_note IS NULL) OR "
            "(status IN ('ACCEPTED','REJECTED') "
            "AND decided_by_user_id IS NOT NULL AND decided_at IS NOT NULL "
            "AND decision_note IS NOT NULL AND length(trim(decision_note)) >= 1)",
            name="ck_replan_proposals_decision_fields",
        ),
    )
    for name, columns in (
        ("ix_replan_proposals_id", ["id"]),
        ("ix_replan_proposals_project_id", ["project_id"]),
        ("ix_replan_proposals_base_plan_version_id", ["base_plan_version_id"]),
        ("ix_replan_proposals_created_by_user_id", ["created_by_user_id"]),
        ("ix_replan_proposals_decided_by_user_id", ["decided_by_user_id"]),
        (
            "ix_replan_proposals_project_status_created",
            ["project_id", "status", "created_at", "id"],
        ),
    ):
        op.create_index(name, "replan_proposals", columns, unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["learning_projects.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["replan_proposals.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.CheckConstraint(
            "event_type IN ('PROPOSAL_CREATED','PROPOSAL_ACCEPTED',"
            "'PROPOSAL_REJECTED')",
            name="ck_audit_events_event_type",
        ),
    )
    for name, columns in (
        ("ix_audit_events_id", ["id"]),
        ("ix_audit_events_project_id", ["project_id"]),
        ("ix_audit_events_proposal_id", ["proposal_id"]),
        ("ix_audit_events_actor_user_id", ["actor_user_id"]),
        ("ix_audit_events_project_created", ["project_id", "created_at", "id"]),
        ("ix_audit_events_proposal_created", ["proposal_id", "created_at", "id"]),
    ):
        op.create_index(name, "audit_events", columns, unique=False)


def downgrade() -> None:
    for name in (
        "ix_audit_events_proposal_created",
        "ix_audit_events_project_created",
        "ix_audit_events_actor_user_id",
        "ix_audit_events_proposal_id",
        "ix_audit_events_project_id",
        "ix_audit_events_id",
    ):
        op.drop_index(name, table_name="audit_events")
    op.drop_table("audit_events")

    for name in (
        "ix_replan_proposals_project_status_created",
        "ix_replan_proposals_decided_by_user_id",
        "ix_replan_proposals_created_by_user_id",
        "ix_replan_proposals_base_plan_version_id",
        "ix_replan_proposals_project_id",
        "ix_replan_proposals_id",
    ):
        op.drop_index(name, table_name="replan_proposals")
    op.drop_table("replan_proposals")