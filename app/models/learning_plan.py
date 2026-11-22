from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LearningPlan(Base):
    __tablename__ = "learning_plans"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_learning_plans_project"),
        CheckConstraint(
            "provider_name IS NULL OR length(trim(provider_name)) BETWEEN 1 AND 80",
            name="ck_learning_plans_provider_name",
        ),
        CheckConstraint(
            "model_name IS NULL OR length(trim(model_name)) BETWEEN 1 AND 160",
            name="ck_learning_plans_model_name",
        ),
        CheckConstraint(
            "(provider_name IS NOT NULL "
            "AND model_name IS NOT NULL) OR "
            "(provider_name IS NULL AND model_name IS NULL)",
            name="ck_learning_plans_model_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("learning_projects.id"), nullable=False, index=True
    )
    # Preserve existing generation metadata. Tasks are read from learning_tasks.
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))