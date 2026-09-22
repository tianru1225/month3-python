from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.replan import AuditEventType, ReplanProposalStatus


NonEmptyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class AddedTaskDiff(BaseModel):
    task_key: NonEmptyText
    title: NonEmptyText
    position: int = Field(gt=0)


class RemovedTaskDiff(BaseModel):
    task_id: int = Field(gt=0)
    title: NonEmptyText


class MovedTaskDiff(BaseModel):
    task_id: int = Field(gt=0)
    from_position: int = Field(gt=0)
    to_position: int = Field(gt=0)


class ChangedTaskDiff(BaseModel):
    task_id: int = Field(gt=0)
    changes: dict[str, object] = Field(min_length=1)


class PlanDiff(BaseModel):
    added: list[AddedTaskDiff] = Field(default_factory=list)
    removed: list[RemovedTaskDiff] = Field(default_factory=list)
    moved: list[MovedTaskDiff] = Field(default_factory=list)
    changed: list[ChangedTaskDiff] = Field(default_factory=list)


class ReplanProposalCreate(BaseModel):
    base_plan_version_id: int = Field(gt=0)
    trigger_code: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
    ]
    proposed_content: dict[str, object] = Field(min_length=1)
    diff: PlanDiff


class ReplanDecisionCreate(BaseModel):
    note: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
    ]


class ReplanProposalResponse(BaseModel):
    id: int
    project_id: int
    base_plan_version_id: int
    created_by_user_id: int | None
    trigger_code: str
    reason: str
    proposed_content: dict[str, object]
    diff: PlanDiff
    status: ReplanProposalStatus
    decided_by_user_id: int | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditEventResponse(BaseModel):
    id: int
    project_id: int
    proposal_id: int
    actor_user_id: int | None
    event_type: AuditEventType
    payload: dict[str, object]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)