from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvidenceType(str, Enum):
    TEXT_ANSWER = "TEXT_ANSWER"
    TEST_REPORT = "TEST_REPORT"


class EvidenceSourceKind(str, Enum):
    USER = "USER"
    AUTOMATION = "AUTOMATION"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "plan_version_id"],
            ["learning_tasks.id", "learning_tasks.plan_version_id"],
            name="fk_evidence_task_version",
        ),
        UniqueConstraint(
            "task_id",
            "attempt_number",
            name="uq_evidence_task_attempt",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_evidence_attempt_number",
        ),
        CheckConstraint(
            "evidence_type IN ('TEXT_ANSWER','TEST_REPORT')",
            name="ck_evidence_type",
        ),
        CheckConstraint(
            "source_kind IN ('USER','AUTOMATION')",
            name="ck_evidence_source_kind",
        ),
        CheckConstraint(
            "(evidence_type = 'TEXT_ANSWER' "
            "AND text_content IS NOT NULL AND test_report IS NULL) OR "
            "(evidence_type = 'TEST_REPORT' "
            "AND text_content IS NULL AND test_report IS NOT NULL)",
            name="ck_evidence_payload",
        ),
        CheckConstraint(
            "text_content IS NULL OR length(trim(text_content)) BETWEEN 1 AND 20000",
            name="ck_evidence_text_content",
        ),
        CheckConstraint(
            "(source_kind = 'USER' AND source_ref IS NULL) OR "
            "(source_kind = 'AUTOMATION' AND source_ref IS NOT NULL "
            "AND length(trim(source_ref)) BETWEEN 1 AND 500)",
            name="ck_evidence_source_ref",
        ),
        Index(
            "ix_evidence_task_submitted",
            "task_id",
            "submitted_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    plan_version_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_report: Mapped[dict[str, object] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    submitted_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
