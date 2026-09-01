from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskPrerequisite


def get_owned_plan_version(
    db: Session, *, plan_version_id: int, user_id: int
) -> PlanVersion | None:
    return db.scalar(
        select(PlanVersion)
        .join(LearningPlan, LearningPlan.id == PlanVersion.plan_id)
        .join(LearningProject, LearningProject.id == LearningPlan.project_id)
        .where(
            PlanVersion.id == plan_version_id,
            LearningProject.user_id == user_id,
        )
    )


def get_task(db: Session, *, plan_version_id: int, task_id: int) -> LearningTask | None:
    return db.scalar(
        select(LearningTask).where(
            LearningTask.id == task_id,
            LearningTask.plan_version_id == plan_version_id,
        )
    )


def get_task_by_position(
    db: Session, *, plan_version_id: int, position: int
) -> LearningTask | None:
    return db.scalar(
        select(LearningTask).where(
            LearningTask.plan_version_id == plan_version_id,
            LearningTask.position == position,
        )
    )


def list_tasks(db: Session, *, plan_version_id: int) -> list[LearningTask]:
    return list(
        db.scalars(
            select(LearningTask)
            .where(LearningTask.plan_version_id == plan_version_id)
            .order_by(
                LearningTask.scheduled_date.asc().nulls_last(),
                LearningTask.position.asc(),
                LearningTask.id.asc(),
            )
        ).all()
    )


def add_task(
    db: Session,
    *,
    plan_version_id: int,
    position: int,
    scheduled_date: date | None,
    title: str,
    objective: str,
    instructions: str,
    steps: list[str],
    estimated_minutes: int,
    deliverable: str,
    acceptance_criteria: list[str],
) -> LearningTask:
    task = LearningTask(
        plan_version_id=plan_version_id,
        position=position,
        scheduled_date=scheduled_date,
        title=title,
        objective=objective,
        instructions=instructions,
        steps=steps,
        estimated_minutes=estimated_minutes,
        deliverable=deliverable,
        acceptance_criteria=acceptance_criteria,
    )
    db.add(task)
    db.flush()
    return task


def list_edges(db: Session, *, plan_version_id: int) -> list[TaskPrerequisite]:
    return list(
        db.scalars(
            select(TaskPrerequisite)
            .where(TaskPrerequisite.plan_version_id == plan_version_id)
            .order_by(TaskPrerequisite.id.asc())
        ).all()
    )


def get_edge(
    db: Session, *, task_id: int, prerequisite_task_id: int
) -> TaskPrerequisite | None:
    return db.scalar(
        select(TaskPrerequisite).where(
            TaskPrerequisite.task_id == task_id,
            TaskPrerequisite.prerequisite_task_id == prerequisite_task_id,
        )
    )


def add_edge(
    db: Session,
    *,
    plan_version_id: int,
    task_id: int,
    prerequisite_task_id: int,
) -> TaskPrerequisite:
    edge = TaskPrerequisite(
        plan_version_id=plan_version_id,
        task_id=task_id,
        prerequisite_task_id=prerequisite_task_id,
    )
    db.add(edge)
    db.flush()
    return edge


def list_prerequisite_ids(db: Session, *, task_id: int) -> list[int]:
    return list(
        db.scalars(
            select(TaskPrerequisite.prerequisite_task_id)
            .where(TaskPrerequisite.task_id == task_id)
            .order_by(TaskPrerequisite.prerequisite_task_id.asc())
        ).all()
    )
