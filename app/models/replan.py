from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReplanProposalStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class AuditEventType(str, Enum):
    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    PROPOSAL_ACCEPTED = "PROPOSAL_ACCEPTED"
    PROPOSAL_REJECTED = "PROPOSAL_REJECTED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReplanProposal(Base):
    __tablename__ = "replan_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','ACCEPTED','REJECTED')",
            name="ck_replan_proposals_status",
        ),
        CheckConstraint(
            "length(trim(trigger_code)) BETWEEN 1 AND 80",
            name="ck_replan_proposals_trigger_code",
        ),
        CheckConstraint(
            "length(trim(reason)) BETWEEN 1 AND 5000",
            name="ck_replan_proposals_reason",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND decided_by_user_id IS NULL "
            "AND decided_at IS NULL AND decision_note IS NULL) OR "
            "(status IN ('ACCEPTED','REJECTED') "
            "AND decided_by_user_id IS NOT NULL AND decided_at IS NOT NULL "
            "AND decision_note IS NOT NULL AND length(trim(decision_note)) >= 1)",
            name="ck_replan_proposals_decision_fields",
        ),
        Index(
            "ix_replan_proposals_project_status_created",
            "project_id",
            "status",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("learning_projects.id"), nullable=False, index=True
    )
    base_plan_version_id: Mapped[int] = mapped_column(
        ForeignKey("plan_versions.id"), nullable=False, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    trigger_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_content: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    diff: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ReplanProposalStatus.PENDING.value, nullable=False
    )
    decided_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('PROPOSAL_CREATED','PROPOSAL_ACCEPTED',"
            "'PROPOSAL_REJECTED')",
            name="ck_audit_events_event_type",
        ),
        Index(
            "ix_audit_events_project_created",
            "project_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_audit_events_proposal_created",
            "proposal_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("learning_projects.id"), nullable=False, index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("replan_proposals.id"), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
