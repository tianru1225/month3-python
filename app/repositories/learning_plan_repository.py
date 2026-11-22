from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan
from app.models.learning_project import LearningProject


def get_owned_plan(
    db: Session, *, plan_id: int, user_id: int, lock: bool = False
) -> LearningPlan | None:
    statement = (
        select(LearningPlan)
        .join(LearningProject, LearningProject.id == LearningPlan.project_id)
        .where(
            LearningPlan.id == plan_id,
            LearningProject.user_id == user_id,
            LearningProject.deleted_at.is_(None),
        )
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return db.scalar(statement)


def get_project_plan(db: Session, *, project_id: int) -> LearningPlan | None:
    return db.scalar(
        select(LearningPlan).where(LearningPlan.project_id == project_id)
    )


def add_plan(
    db: Session, *, project_id: int, content: dict,
    provider_name: str | None, model_name: str | None,
) -> LearningPlan:
    plan = LearningPlan(
        project_id=project_id, content=content,
        provider_name=provider_name, model_name=model_name,
    )
    db.add(plan)
    db.flush()
    return plan