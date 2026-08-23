from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LearningProject(Base):
    __tablename__ = "learning_projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','PAUSED','COMPLETED','ARCHIVED')",
            name="ck_learning_projects_status",
        ),
        CheckConstraint(
            "daily_minutes BETWEEN 1 AND 1440",
            name="ck_learning_projects_daily_minutes",
        ),
        CheckConstraint(
            "weekly_days BETWEEN 1 AND 7",
            name="ck_learning_projects_weekly_days",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    current_level: Mapped[str] = mapped_column(String(40), nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    weekly_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    expected_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=ProjectStatus.ACTIVE.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
