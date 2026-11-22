from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan
from app.models.learning_project import LearningProject
from app.models.material import Material
from app.models.project_material import ProjectMaterialBinding
from app.repositories.learning_plan_repository import (
    add_plan, get_owned_plan, get_project_plan,
)
from app.schemas.learning_plan import PlanCreate


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _require_project_owner(
    db: Session, *, project_id: int, user_id: int
) -> LearningProject:
    project = db.scalar(
        select(LearningProject).where(LearningProject.id == project_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if project is None or project.user_id != user_id or project.deleted_at is not None:
        raise _error("PROJECT_NOT_FOUND", "project not found", 404)
    pending = db.scalar(
        select(Material.id)
        .join(ProjectMaterialBinding, ProjectMaterialBinding.material_id == Material.id)
        .where(
            ProjectMaterialBinding.project_id == project_id,
            Material.deletion_started_at.is_not(None),
        ).limit(1)
    )
    if pending is not None:
        raise _error("MATERIAL_CLEANUP_PENDING", "finish pending material cleanup", 409)
    return project


def create_plan(
    db: Session, *, project_id: int, user_id: int, payload: PlanCreate
) -> LearningPlan:
    # Internal creation primitive; model generation and atomic replacement follow later.
    try:
        _require_project_owner(db, project_id=project_id, user_id=user_id)
        if get_project_plan(db, project_id=project_id) is not None:
            raise _error("PROJECT_PLAN_EXISTS", "project already has a plan", 409)
        plan = add_plan(
            db, project_id=project_id, content=payload.content,
            provider_name=payload.provider_name, model_name=payload.model_name,
        )
        db.commit()
        db.refresh(plan)
        return plan
    except Exception:
        db.rollback()
        raise


def get_plan(db: Session, *, plan_id: int, user_id: int) -> LearningPlan:
    plan = get_owned_plan(db, plan_id=plan_id, user_id=user_id)
    if plan is None:
        raise _error("PLAN_NOT_FOUND", "plan not found", 404)
    return plan


def start_plan(db: Session, *, plan_id: int, user_id: int) -> LearningPlan:
    # Internal lock operation. Browser entry and generation races are the next card.
    try:
        plan = get_owned_plan(db, plan_id=plan_id, user_id=user_id, lock=True)
        if plan is None:
            raise _error("PLAN_NOT_FOUND", "plan not found", 404)
        if plan.locked_at is None:
            plan.locked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(plan)
        return plan
    except Exception:
        db.rollback()
        raise