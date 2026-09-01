from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Date,
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


class TaskStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    PASSED = "PASSED"
    REVISION_REQUIRED = "REVISION_REQUIRED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LearningTask(Base):
    __tablename__ = "learning_tasks"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "plan_version_id",
            name="uq_learning_tasks_id_plan_version",
        ),
        UniqueConstraint(
            "plan_version_id",
            "position",
            name="uq_learning_tasks_version_position",
        ),
        CheckConstraint(
            "position >= 1",
            name="ck_learning_tasks_position",
        ),
        CheckConstraint(
            "estimated_minutes BETWEEN 1 AND 1440",
            name="ck_learning_tasks_estimated_minutes",
        ),
        CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 160",
            name="ck_learning_tasks_title",
        ),
        CheckConstraint(
            "length(trim(objective)) BETWEEN 1 AND 5000",
            name="ck_learning_tasks_objective",
        ),
        CheckConstraint(
            "length(trim(instructions)) BETWEEN 1 AND 10000",
            name="ck_learning_tasks_instructions",
        ),
        CheckConstraint(
            "length(trim(deliverable)) BETWEEN 1 AND 5000",
            name="ck_learning_tasks_deliverable",
        ),
        CheckConstraint(
            "status IN "
            "('DRAFT','READY','IN_PROGRESS','SUBMITTED','PASSED',"
            "'REVISION_REQUIRED')",
            name="ck_learning_tasks_status",
        ),
        CheckConstraint(
            "(status = 'PASSED' AND completed_at IS NOT NULL) OR "
            "(status <> 'PASSED' AND completed_at IS NULL)",
            name="ck_learning_tasks_completed_at",
        ),
        Index(
            "ix_learning_tasks_version_date_position",
            "plan_version_id",
            "scheduled_date",
            "position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    plan_version_id: Mapped[int] = mapped_column(
        ForeignKey("plan_versions.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    deliverable: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=TaskStatus.DRAFT.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TaskPrerequisite(Base):
    __tablename__ = "task_prerequisites"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "plan_version_id"],
            ["learning_tasks.id", "learning_tasks.plan_version_id"],
            name="fk_task_prerequisites_task_version",
        ),
        ForeignKeyConstraint(
            ["prerequisite_task_id", "plan_version_id"],
            ["learning_tasks.id", "learning_tasks.plan_version_id"],
            name="fk_task_prerequisites_prerequisite_version",
        ),
        UniqueConstraint(
            "task_id",
            "prerequisite_task_id",
            name="uq_task_prerequisites_edge",
        ),
        CheckConstraint(
            "task_id <> prerequisite_task_id",
            name="ck_task_prerequisites_not_self",
        ),
        Index("ix_task_prerequisites_task_id", "task_id"),
        Index(
            "ix_task_prerequisites_prerequisite_task_id",
            "prerequisite_task_id",
        ),
        Index("ix_task_prerequisites_plan_version_id", "plan_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    plan_version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False)
    prerequisite_task_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
