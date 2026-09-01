from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.learning_plan import (
    LearningPlan,
    PlanVersion,
    PlanVersionStatus,
)
from app.models.learning_project import LearningProject
from app.repositories.learning_plan_repository import (
    add_plan,
    add_version,
    clear_current_version,
    get_current_version,
    get_next_version_number,
    get_owned_plan,
    get_owned_version,
    list_versions,
)
from app.schemas.learning_plan import PlanCreate, PlanReject, PlanVersionCreate


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_project_owner(
    db: Session, *, project_id: int, user_id: int
) -> LearningProject:
    project = db.get(LearningProject, project_id)
    if project is None or project.user_id != user_id:
        raise _error(
            "PROJECT_NOT_FOUND", "project not found", status.HTTP_404_NOT_FOUND
        )
    return project


def create_plan_with_first_draft(
    db: Session, *, project_id: int, user_id: int, payload: PlanCreate
) -> tuple[LearningPlan, PlanVersion]:
    _require_project_owner(db, project_id=project_id, user_id=user_id)
    try:
        plan = add_plan(db, project_id=project_id, name=payload.name)
        version = add_version(
            db,
            plan_id=plan.id,
            version_number=1,
            goal=payload.goal,
            content=payload.content,
            source_kind=payload.source_kind.value,
            provider_name=payload.provider_name,
            model_name=payload.model_name,
        )
        db.commit()
        db.refresh(plan)
        db.refresh(version)
        return plan, version
    except Exception:
        db.rollback()
        raise


def create_next_draft(
    db: Session, *, plan_id: int, user_id: int, payload: PlanVersionCreate
) -> PlanVersion:
    plan = get_owned_plan(db, plan_id=plan_id, user_id=user_id)
    if plan is None:
        raise _error("PLAN_NOT_FOUND", "plan not found", status.HTTP_404_NOT_FOUND)
    try:
        version = add_version(
            db,
            plan_id=plan.id,
            version_number=get_next_version_number(db, plan_id=plan.id),
            goal=payload.goal,
            content=payload.content,
            source_kind=payload.source_kind.value,
            provider_name=payload.provider_name,
            model_name=payload.model_name,
        )
        db.commit()
        db.refresh(version)
        return version
    except Exception:
        db.rollback()
        raise


def publish_version(
    db: Session, *, plan_id: int, version_id: int, user_id: int
) -> PlanVersion:
    plan = get_owned_plan(db, plan_id=plan_id, user_id=user_id)
    version = get_owned_version(db, version_id=version_id, user_id=user_id)
    if plan is None or version is None or version.plan_id != plan.id:
        raise _error(
            "PLAN_VERSION_NOT_FOUND",
            "plan version not found",
            status.HTTP_404_NOT_FOUND,
        )
    if version.status != PlanVersionStatus.DRAFT.value:
        raise _error(
            "PLAN_VERSION_IMMUTABLE",
            "only a draft plan version can be published",
            status.HTTP_409_CONFLICT,
        )
    try:
        clear_current_version(db, plan_id=plan.id)
        version.status = PlanVersionStatus.PUBLISHED.value
        version.is_current = True
        version.published_at = _now()
        version.confirmed_by_user_id = user_id
        db.commit()
        db.refresh(version)
        return version
    except Exception:
        db.rollback()
        raise


def reject_draft(
    db: Session,
    *,
    plan_id: int,
    version_id: int,
    user_id: int,
    payload: PlanReject,
) -> PlanVersion:
    plan = get_owned_plan(db, plan_id=plan_id, user_id=user_id)
    version = get_owned_version(db, version_id=version_id, user_id=user_id)
    if plan is None or version is None or version.plan_id != plan.id:
        raise _error(
            "PLAN_VERSION_NOT_FOUND",
            "plan version not found",
            status.HTTP_404_NOT_FOUND,
        )
    if version.status != PlanVersionStatus.DRAFT.value:
        raise _error(
            "PLAN_VERSION_IMMUTABLE",
            "only a draft plan version can be rejected",
            status.HTTP_409_CONFLICT,
        )
    try:
        version.status = PlanVersionStatus.REJECTED.value
        version.rejection_reason = payload.reason
        version.is_current = False
        db.commit()
        db.refresh(version)
        return version
    except Exception:
        db.rollback()
        raise


def get_current_published_version(
    db: Session, *, plan_id: int, user_id: int
) -> PlanVersion | None:
    plan = get_owned_plan(db, plan_id=plan_id, user_id=user_id)
    if plan is None:
        raise _error("PLAN_NOT_FOUND", "plan not found", status.HTTP_404_NOT_FOUND)
    return get_current_version(db, plan_id=plan.id)


def list_plan_versions(db: Session, *, plan_id: int, user_id: int) -> list[PlanVersion]:
    plan = get_owned_plan(db, plan_id=plan_id, user_id=user_id)
    if plan is None:
        raise _error("PLAN_NOT_FOUND", "plan not found", status.HTTP_404_NOT_FOUND)
    return list_versions(db, plan_id=plan.id)
