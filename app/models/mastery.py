from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MasteryLevel(str, Enum):
    NOVICE = "NOVICE"
    DEVELOPING = "DEVELOPING"
    PROFICIENT = "PROFICIENT"
    MASTERED = "MASTERED"


class ReviewItemStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MasteryRecord(Base):
    __tablename__ = "mastery_records"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id",
            name="uq_mastery_records_evaluation_id",
        ),
        CheckConstraint(
            "score_before BETWEEN 0 AND 100",
            name="ck_mastery_records_score_before",
        ),
        CheckConstraint(
            "score_after BETWEEN 0 AND 100",
            name="ck_mastery_records_score_after",
        ),
        CheckConstraint(
            "level_after IN ('NOVICE','DEVELOPING','PROFICIENT','MASTERED')",
            name="ck_mastery_records_level_after",
        ),
        CheckConstraint(
            "decision IN ('PASSED','REVISION_REQUIRED')",
            name="ck_mastery_records_decision",
        ),
        CheckConstraint(
            "interval_days BETWEEN 1 AND 3650",
            name="ck_mastery_records_interval_days",
        ),
        CheckConstraint(
            "length(trim(algorithm_version)) BETWEEN 1 AND 80",
            name="ck_mastery_records_algorithm_version",
        ),
        CheckConstraint(
            "length(trim(reason)) BETWEEN 1 AND 5000",
            name="ck_mastery_records_reason",
        ),
        Index(
            "ix_mastery_records_project_node_recorded",
            "project_id",
            "knowledge_node_id",
            "recorded_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("learning_projects.id"), nullable=False, index=True
    )
    knowledge_node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id"), nullable=False, index=True
    )
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id"), nullable=False, index=True
    )
    score_before: Mapped[int] = mapped_column(Integer, nullable=False)
    score_after: Mapped[int] = mapped_column(Integer, nullable=False)
    level_after: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    next_review_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    calculation: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "knowledge_node_id",
            name="uq_review_items_project_node",
        ),
        UniqueConstraint(
            "last_record_id",
            name="uq_review_items_last_record_id",
        ),
        CheckConstraint(
            "mastery_score BETWEEN 0 AND 100",
            name="ck_review_items_mastery_score",
        ),
        CheckConstraint(
            "mastery_level IN ('NOVICE','DEVELOPING','PROFICIENT','MASTERED')",
            name="ck_review_items_mastery_level",
        ),
        CheckConstraint(
            "status IN ('PENDING','COMPLETED')",
            name="ck_review_items_status",
        ),
        CheckConstraint(
            "interval_days BETWEEN 1 AND 3650",
            name="ck_review_items_interval_days",
        ),
        CheckConstraint(
            "review_count >= 0",
            name="ck_review_items_review_count",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND completed_at IS NULL) OR "
            "(status = 'COMPLETED' AND completed_at IS NOT NULL "
            "AND last_reviewed_at IS NOT NULL)",
            name="ck_review_items_completion_fields",
        ),
        Index(
            "ix_review_items_project_due",
            "project_id",
            "status",
            "next_review_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("learning_projects.id"), nullable=False, index=True
    )
    knowledge_node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id"), nullable=False, index=True
    )
    last_record_id: Mapped[int] = mapped_column(
        ForeignKey("mastery_records.id"), nullable=False, index=True
    )
    mastery_score: Mapped[int] = mapped_column(Integer, nullable=False)
    mastery_level: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ReviewItemStatus.PENDING.value, nullable=False
    )
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    next_review_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
