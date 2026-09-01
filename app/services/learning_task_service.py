from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.learning_plan import PlanVersion, PlanVersionStatus
from app.models.learning_task import LearningTask, TaskPrerequisite
from app.repositories.learning_task_repository import (
    add_edge,
    add_task,
    get_edge,
    get_owned_plan_version,
    get_task,
    get_task_by_position,
    list_edges,
    list_prerequisite_ids,
    list_tasks,
)
from app.schemas.learning_task import LearningTaskCreate


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _get_owned_version_or_raise(
    db: Session, *, plan_version_id: int, user_id: int
) -> PlanVersion:
    version = get_owned_plan_version(
        db,
        plan_version_id=plan_version_id,
        user_id=user_id,
    )
    if version is None:
        raise _error(
            "PLAN_VERSION_NOT_FOUND",
            "plan version not found",
            status.HTTP_404_NOT_FOUND,
        )
    return version


def _require_draft(version: PlanVersion) -> None:
    if version.status != PlanVersionStatus.DRAFT.value:
        raise _error(
            "PLAN_VERSION_IMMUTABLE",
            "tasks can only be changed on a draft plan version",
            status.HTTP_409_CONFLICT,
        )


def create_task(
    db: Session,
    *,
    plan_version_id: int,
    user_id: int,
    payload: LearningTaskCreate,
) -> LearningTask:
    version = _get_owned_version_or_raise(
        db,
        plan_version_id=plan_version_id,
        user_id=user_id,
    )
    _require_draft(version)
    if (
        get_task_by_position(
            db,
            plan_version_id=plan_version_id,
            position=payload.position,
        )
        is not None
    ):
        raise _error(
            "TASK_POSITION_CONFLICT",
            "task position already exists in this plan version",
            status.HTTP_409_CONFLICT,
        )
    try:
        task = add_task(
            db,
            plan_version_id=plan_version_id,
            position=payload.position,
            scheduled_date=payload.scheduled_date,
            title=payload.title,
            objective=payload.objective,
            instructions=payload.instructions,
            steps=payload.steps,
            estimated_minutes=payload.estimated_minutes,
            deliverable=payload.deliverable,
            acceptance_criteria=payload.acceptance_criteria,
        )
        db.commit()
        db.refresh(task)
        return task
    except Exception:
        db.rollback()
        raise


def list_version_tasks(
    db: Session, *, plan_version_id: int, user_id: int
) -> list[LearningTask]:
    _get_owned_version_or_raise(
        db,
        plan_version_id=plan_version_id,
        user_id=user_id,
    )
    return list_tasks(db, plan_version_id=plan_version_id)


def _would_create_cycle(
    edges: list[TaskPrerequisite],
    *,
    task_id: int,
    prerequisite_task_id: int,
) -> bool:
    graph: dict[int, set[int]] = {}
    for edge in edges:
        graph.setdefault(edge.task_id, set()).add(edge.prerequisite_task_id)

    stack = [prerequisite_task_id]
    visited: set[int] = set()
    while stack:
        current = stack.pop()
        if current == task_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(graph.get(current, set()))
    return False


def add_task_prerequisite(
    db: Session,
    *,
    plan_version_id: int,
    task_id: int,
    prerequisite_task_id: int,
    user_id: int,
) -> tuple[TaskPrerequisite, bool]:
    version = _get_owned_version_or_raise(
        db,
        plan_version_id=plan_version_id,
        user_id=user_id,
    )
    _require_draft(version)

    task = get_task(
        db,
        plan_version_id=plan_version_id,
        task_id=task_id,
    )
    prerequisite = get_task(
        db,
        plan_version_id=plan_version_id,
        task_id=prerequisite_task_id,
    )
    if task is None or prerequisite is None:
        raise _error(
            "LEARNING_TASK_NOT_FOUND",
            "learning task not found in this plan version",
            status.HTTP_404_NOT_FOUND,
        )
    if task.id == prerequisite.id:
        raise _error(
            "TASK_PREREQUISITE_INVALID",
            "task cannot depend on itself",
            status.HTTP_400_BAD_REQUEST,
        )

    existing = get_edge(
        db,
        task_id=task.id,
        prerequisite_task_id=prerequisite.id,
    )
    if existing is not None:
        return existing, False

    if _would_create_cycle(
        list_edges(db, plan_version_id=plan_version_id),
        task_id=task.id,
        prerequisite_task_id=prerequisite.id,
    ):
        raise _error(
            "TASK_PREREQUISITE_CYCLE",
            "task prerequisite would create a cycle",
            status.HTTP_409_CONFLICT,
        )

    try:
        edge = add_edge(
            db,
            plan_version_id=plan_version_id,
            task_id=task.id,
            prerequisite_task_id=prerequisite.id,
        )
        db.commit()
        db.refresh(edge)
        return edge, True
    except Exception:
        db.rollback()
        raise


def get_task_prerequisite_ids(
    db: Session,
    *,
    plan_version_id: int,
    task_id: int,
    user_id: int,
) -> list[int]:
    _get_owned_version_or_raise(
        db,
        plan_version_id=plan_version_id,
        user_id=user_id,
    )
    task = get_task(
        db,
        plan_version_id=plan_version_id,
        task_id=task_id,
    )
    if task is None:
        raise _error(
            "LEARNING_TASK_NOT_FOUND",
            "learning task not found in this plan version",
            status.HTTP_404_NOT_FOUND,
        )
    return list_prerequisite_ids(db, task_id=task.id)
