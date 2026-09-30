from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.learning_task import LearningTask, TaskStatus
from app.repositories.today_task_repository import (
    get_current_published_version_for_project,
    list_prerequisite_states,
    list_tasks_for_date,
)
from app.schemas.today_task import (
    PrerequisiteTaskStatus,
    TodayTaskResponse,
    TodayTasksResponse,
)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "PLAN_VERSION_NOT_FOUND",
            "message": "current published plan version not found",
        },
    )


def _to_response(
    task: LearningTask, states: list[PrerequisiteTaskStatus]
) -> TodayTaskResponse:
    return TodayTaskResponse(
        id=task.id,
        plan_version_id=task.plan_version_id,
        position=task.position,
        scheduled_date=task.scheduled_date,
        title=task.title,
        objective=task.objective,
        instructions=task.instructions,
        steps=task.steps,
        estimated_minutes=task.estimated_minutes,
        deliverable=task.deliverable,
        acceptance_criteria=task.acceptance_criteria,
        status=TaskStatus(task.status),
        created_at=task.created_at,
        completed_at=task.completed_at,
        prerequisites=states,
        prerequisites_complete=all(
            state.status is TaskStatus.PASSED for state in states
        ),
    )


def list_today_tasks_or_raise(
    db: Session,
    *,
    project_id: int,
    plan_version_id: int,
    user_id: int,
    target_date: date,
) -> TodayTasksResponse:
    version = get_current_published_version_for_project(
        db,
        project_id=project_id,
        plan_version_id=plan_version_id,
        user_id=user_id,
    )
    if version is None:
        raise _not_found()

    tasks: list[TodayTaskResponse] = []
    for task in list_tasks_for_date(
        db, plan_version_id=version.id, target_date=target_date
    ):
        raw_states = list_prerequisite_states(
            db, plan_version_id=version.id, task_id=task.id
        )
        states = [
            PrerequisiteTaskStatus(
                task_id=task_id,
                status=TaskStatus(raw_status),
            )
            for task_id, raw_status in raw_states
        ]
        tasks.append(_to_response(task, states))

    return TodayTasksResponse(
        project_id=project_id,
        plan_version_id=version.id,
        target_date=target_date,
        tasks=tasks,
    )
