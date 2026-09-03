from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RuleEvaluationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class EvaluationDecision(str, Enum):
    PASSED = "PASSED"
    REVISION_REQUIRED = "REVISION_REQUIRED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("evidence_id", name="uq_evaluations_evidence_id"),
        CheckConstraint(
            "rule_status IN ('PASS','FAIL','INCONCLUSIVE')",
            name="ck_evaluations_rule_status",
        ),
        CheckConstraint(
            "human_decision IS NULL OR human_decision IN "
            "('PASSED','REVISION_REQUIRED')",
            name="ck_evaluations_human_decision",
        ),
        CheckConstraint(
            "final_decision IS NULL OR final_decision IN "
            "('PASSED','REVISION_REQUIRED')",
            name="ck_evaluations_final_decision",
        ),
        CheckConstraint(
            "(human_decision IS NULL AND human_note IS NULL "
            "AND confirmed_by_user_id IS NULL AND confirmed_at IS NULL) OR "
            "(human_decision IS NOT NULL AND human_note IS NOT NULL "
            "AND confirmed_by_user_id IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_evaluations_human_fields",
        ),
        CheckConstraint(
            "(final_decision IS NULL AND finalized_by_user_id IS NULL "
            "AND finalized_at IS NULL) OR "
            "(final_decision IS NOT NULL AND finalized_by_user_id IS NOT NULL "
            "AND finalized_at IS NOT NULL)",
            name="ck_evaluations_final_fields",
        ),
        CheckConstraint(
            "final_decision IS NULL OR human_decision IS NOT NULL",
            name="ck_evaluations_final_requires_human",
        ),
        CheckConstraint(
            "final_decision IS NULL OR final_decision = human_decision",
            name="ck_evaluations_final_matches_human",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence.id"), nullable=False, index=True
    )
    rule_status: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_result: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    model_suggestion: Mapped[dict[str, object] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    human_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    human_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    final_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    finalized_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
