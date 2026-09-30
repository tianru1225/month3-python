from datetime import date

from pydantic import BaseModel

from app.models.learning_task import TaskStatus
from app.schemas.learning_task import LearningTaskResponse


class PrerequisiteTaskStatus(BaseModel):
    task_id: int
    status: TaskStatus


class TodayTaskResponse(LearningTaskResponse):
    prerequisites: list[PrerequisiteTaskStatus]
    prerequisites_complete: bool


class TodayTasksResponse(BaseModel):
    project_id: int
    plan_version_id: int
    target_date: date
    tasks: list[TodayTaskResponse]
