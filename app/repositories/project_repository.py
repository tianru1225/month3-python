from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_project import LearningProject
from app.schemas.project import ProjectCreate


def create_project(
    db: Session,
    *,
    user_id: int,
    payload: ProjectCreate,
) -> LearningProject:
    project = LearningProject(
        user_id=user_id,
        **payload.model_dump(),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects_by_user(
    db: Session,
    *,
    user_id: int,
) -> list[LearningProject]:
    statement = (
        select(LearningProject)
        .where(LearningProject.user_id == user_id)
        .order_by(LearningProject.created_at.desc(), LearningProject.id.desc())
    )
    return list(db.scalars(statement).all())


def get_project_by_id_and_user(
    db: Session,
    *,
    project_id: int,
    user_id: int,
) -> LearningProject | None:
    statement = select(LearningProject).where(
        LearningProject.id == project_id,
        LearningProject.user_id == user_id,
    )
    return db.scalar(statement)
