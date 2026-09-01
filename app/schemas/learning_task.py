from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.learning_task import TaskStatus


TaskTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
]
TaskObjective = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]
TaskInstructions = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)
]
TaskDeliverable = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]
TaskStep = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
AcceptanceCriterion = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class LearningTaskCreate(BaseModel):
    position: int = Field(ge=1)
    scheduled_date: date | None = None
    title: TaskTitle
    objective: TaskObjective
    instructions: TaskInstructions
    steps: list[TaskStep] = Field(min_length=1, max_length=50)
    estimated_minutes: int = Field(ge=1, le=1440)
    deliverable: TaskDeliverable
    acceptance_criteria: list[AcceptanceCriterion] = Field(
        min_length=1,
        max_length=20,
    )


class LearningTaskResponse(BaseModel):
    id: int
    plan_version_id: int
    position: int
    scheduled_date: date | None
    title: str
    objective: str
    instructions: str
    steps: list[str]
    estimated_minutes: int
    deliverable: str
    acceptance_criteria: list[str]
    status: TaskStatus
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class LearningTaskDetailResponse(LearningTaskResponse):
    prerequisite_task_ids: list[int]


class TaskPrerequisiteResponse(BaseModel):
    id: int
    plan_version_id: int
    task_id: int
    prerequisite_task_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
