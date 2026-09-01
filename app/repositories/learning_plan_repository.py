from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject


def get_owned_plan(db: Session, *, plan_id: int, user_id: int) -> LearningPlan | None:
    return db.scalar(
        select(LearningPlan)
        .join(LearningProject, LearningProject.id == LearningPlan.project_id)
        .where(
            LearningPlan.id == plan_id,
            LearningProject.user_id == user_id,
        )
    )


def get_owned_version(
    db: Session, *, version_id: int, user_id: int
) -> PlanVersion | None:
    return db.scalar(
        select(PlanVersion)
        .join(LearningPlan, LearningPlan.id == PlanVersion.plan_id)
        .join(LearningProject, LearningProject.id == LearningPlan.project_id)
        .where(
            PlanVersion.id == version_id,
            LearningProject.user_id == user_id,
        )
    )


def list_versions(db: Session, *, plan_id: int) -> list[PlanVersion]:
    return list(
        db.scalars(
            select(PlanVersion)
            .where(PlanVersion.plan_id == plan_id)
            .order_by(PlanVersion.version_number.asc())
        ).all()
    )


def get_current_version(db: Session, *, plan_id: int) -> PlanVersion | None:
    return db.scalar(
        select(PlanVersion).where(
            PlanVersion.plan_id == plan_id,
            PlanVersion.is_current.is_(True),
        )
    )


def get_next_version_number(db: Session, *, plan_id: int) -> int:
    latest = db.scalar(
        select(func.max(PlanVersion.version_number)).where(
            PlanVersion.plan_id == plan_id
        )
    )
    return (latest or 0) + 1


def add_plan(db: Session, *, project_id: int, name: str) -> LearningPlan:
    plan = LearningPlan(project_id=project_id, name=name)
    db.add(plan)
    db.flush()
    return plan


def add_version(
    db: Session,
    *,
    plan_id: int,
    version_number: int,
    goal: str,
    content: dict,
    source_kind: str,
    provider_name: str | None,
    model_name: str | None,
) -> PlanVersion:
    version = PlanVersion(
        plan_id=plan_id,
        version_number=version_number,
        goal=goal,
        content=content,
        source_kind=source_kind,
        provider_name=provider_name,
        model_name=model_name,
    )
    db.add(version)
    db.flush()
    return version


def clear_current_version(db: Session, *, plan_id: int) -> None:
    current = get_current_version(db, plan_id=plan_id)
    if current is not None:
        current.is_current = False
        db.flush()
