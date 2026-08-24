from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.learning_project import LearningProject
from app.repositories.project_repository import (
    create_project,
    get_project_by_id_and_user,
    list_projects_by_user,
)
from app.schemas.project import ProjectCreate


def create_project_or_raise(
    db: Session,
    *,
    user_id: int,
    payload: ProjectCreate,
) -> LearningProject:
    return create_project(db, user_id=user_id, payload=payload)


def list_projects_for_user(
    db: Session,
    *,
    user_id: int,
) -> list[LearningProject]:
    return list_projects_by_user(db, user_id=user_id)


def get_project_or_raise(
    db: Session,
    *,
    project_id: int,
    user_id: int,
) -> LearningProject:
    project = get_project_by_id_and_user(
        db,
        project_id=project_id,
        user_id=user_id,
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PROJECT_NOT_FOUND",
                "message": "project not found",
            },
        )
    return project
