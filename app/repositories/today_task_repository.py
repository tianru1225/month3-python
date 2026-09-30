from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan, PlanVersion, PlanVersionStatus
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskPrerequisite


def get_current_published_version_for_project(
    db: Session, *, project_id: int, plan_version_id: int, user_id: int
) -> PlanVersion | None:
    statement = (
        select(PlanVersion)
        .join(LearningPlan, LearningPlan.id == PlanVersion.plan_id)
        .join(LearningProject, LearningProject.id == LearningPlan.project_id)
        .where(
            PlanVersion.id == plan_version_id,
            LearningPlan.project_id == project_id,
            LearningProject.user_id == user_id,
            PlanVersion.status == PlanVersionStatus.PUBLISHED.value,
            PlanVersion.is_current.is_(True),
        )
    )
    return db.scalar(statement)


def list_tasks_for_date(
    db: Session, *, plan_version_id: int, target_date: date
) -> list[LearningTask]:
    statement = (
        select(LearningTask)
        .where(
            LearningTask.plan_version_id == plan_version_id,
            LearningTask.scheduled_date == target_date,
        )
        .order_by(LearningTask.position.asc(), LearningTask.id.asc())
    )
    return list(db.scalars(statement).all())


def list_prerequisite_states(
    db: Session, *, plan_version_id: int, task_id: int
) -> list[tuple[int, str]]:
    statement = (
        select(TaskPrerequisite.prerequisite_task_id, LearningTask.status)
        .join(
            LearningTask,
            LearningTask.id == TaskPrerequisite.prerequisite_task_id,
        )
        .where(
            TaskPrerequisite.plan_version_id == plan_version_id,
            TaskPrerequisite.task_id == task_id,
            LearningTask.plan_version_id == plan_version_id,
        )
        .order_by(TaskPrerequisite.prerequisite_task_id.asc())
    )
    return [
        (int(prerequisite_task_id), str(status))
        for prerequisite_task_id, status in db.execute(statement).all()
    ]
