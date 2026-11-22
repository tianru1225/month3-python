from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskPrerequisite


def get_plan_for_project(
    db: Session, *, project_id: int, plan_id: int, user_id: int
) -> LearningPlan | None:
    statement = (
        select(LearningPlan)
        .join(LearningProject, LearningProject.id == LearningPlan.project_id)
        .where(
            LearningPlan.id == plan_id,
            LearningPlan.project_id == project_id,
            LearningProject.user_id == user_id,
            LearningProject.deleted_at.is_(None),
        )
    )
    return db.scalar(statement)


def list_tasks_for_date(
    db: Session, *, plan_id: int, target_date: date
) -> list[LearningTask]:
    statement = (
        select(LearningTask)
        .where(
            LearningTask.plan_id == plan_id,
            LearningTask.scheduled_date == target_date,
        )
        .order_by(LearningTask.position.asc(), LearningTask.id.asc())
    )
    return list(db.scalars(statement).all())


def list_prerequisite_states(
    db: Session, *, plan_id: int, task_id: int
) -> list[tuple[int, str]]:
    statement = (
        select(TaskPrerequisite.prerequisite_task_id, LearningTask.status)
        .join(
            LearningTask,
            LearningTask.id == TaskPrerequisite.prerequisite_task_id,
        )
        .where(
            TaskPrerequisite.plan_id == plan_id,
            TaskPrerequisite.task_id == task_id,
            LearningTask.plan_id == plan_id,
        )
        .order_by(TaskPrerequisite.prerequisite_task_id.asc())
    )
    return [
        (int(prerequisite_task_id), str(status))
        for prerequisite_task_id, status in db.execute(statement).all()
    ]