from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index
from sqlalchemy import JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlanVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"


class PlanSourceKind(str, Enum):
    MANUAL = "MANUAL"
    TEMPLATE = "TEMPLATE"
    MODEL = "MODEL"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LearningPlan(Base):
    __tablename__ = "learning_plans"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 160",
            name="ck_learning_plans_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("learning_projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PlanVersion(Base):
    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint("plan_id", "version_number", name="uq_plan_versions_number"),
        CheckConstraint(
            "version_number >= 1",
            name="ck_plan_versions_version_number",
        ),
        CheckConstraint(
            "length(trim(goal)) BETWEEN 1 AND 5000",
            name="ck_plan_versions_goal",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','REJECTED')",
            name="ck_plan_versions_status",
        ),
        CheckConstraint(
            "source_kind IN ('MANUAL','TEMPLATE','MODEL')",
            name="ck_plan_versions_source_kind",
        ),
        CheckConstraint(
            "provider_name IS NULL OR length(trim(provider_name)) BETWEEN 1 AND 80",
            name="ck_plan_versions_provider_name",
        ),
        CheckConstraint(
            "model_name IS NULL OR length(trim(model_name)) BETWEEN 1 AND 160",
            name="ck_plan_versions_model_name",
        ),
        CheckConstraint(
            "(source_kind = 'MODEL' AND provider_name IS NOT NULL "
            "AND model_name IS NOT NULL) OR "
            "(source_kind <> 'MODEL' AND provider_name IS NULL "
            "AND model_name IS NULL)",
            name="ck_plan_versions_model_identity",
        ),
        CheckConstraint(
            "(status = 'DRAFT' AND is_current = false "
            "AND published_at IS NULL AND confirmed_by_user_id IS NULL "
            "AND rejection_reason IS NULL) OR "
            "(status = 'PUBLISHED' AND published_at IS NOT NULL "
            "AND confirmed_by_user_id IS NOT NULL "
            "AND rejection_reason IS NULL) OR "
            "(status = 'REJECTED' AND is_current = false "
            "AND published_at IS NULL AND confirmed_by_user_id IS NULL "
            "AND rejection_reason IS NOT NULL "
            "AND length(trim(rejection_reason)) BETWEEN 1 AND 2000)",
            name="ck_plan_versions_state_fields",
        ),
        Index("ix_plan_versions_status", "status"),
        Index(
            "uq_plan_versions_current",
            "plan_id",
            unique=True,
            postgresql_where=text("is_current = true"),
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("learning_plans.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=PlanVersionStatus.DRAFT.value, nullable=False
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_kind: Mapped[str] = mapped_column(
        String(20), default=PlanSourceKind.MANUAL.value, nullable=False
    )
    provider_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
