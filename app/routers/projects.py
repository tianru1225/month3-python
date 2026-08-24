from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.deps.auth import get_current_user
from app.deps.db import get_db
from app.models.learning_project import LearningProject
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services.project_service import (
    create_project_or_raise,
    get_project_or_raise,
    list_projects_for_user,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建学习项目",
)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LearningProject:
    return create_project_or_raise(
        db,
        user_id=current_user.id,
        payload=payload,
    )


@router.get(
    "",
    response_model=list[ProjectResponse],
    summary="列出当前用户的学习项目",
)
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LearningProject]:
    return list_projects_for_user(db, user_id=current_user.id)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="查询当前用户的学习项目",
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LearningProject:
    return get_project_or_raise(
        db,
        project_id=project_id,
        user_id=current_user.id,
    )
