from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.learning_plan import PlanSourceKind, PlanVersionStatus


PlanName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
]
PlanGoal = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]
RejectReason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
ProviderName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
ModelName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
]


class PlanCreate(BaseModel):
    name: PlanName
    goal: PlanGoal
    content: dict[str, Any] = Field(default_factory=dict)
    source_kind: PlanSourceKind = PlanSourceKind.MANUAL
    provider_name: ProviderName | None = None
    model_name: ModelName | None = None

    def model_post_init(self, __context: Any) -> None:
        has_model_identity = (
            self.provider_name is not None and self.model_name is not None
        )
        if self.source_kind is PlanSourceKind.MODEL and not has_model_identity:
            raise ValueError("MODEL source requires provider_name and model_name")
        if self.source_kind is not PlanSourceKind.MODEL and (
            self.provider_name is not None or self.model_name is not None
        ):
            raise ValueError("provider_name and model_name require MODEL source")


class PlanVersionCreate(BaseModel):
    goal: PlanGoal
    content: dict[str, Any] = Field(default_factory=dict)
    source_kind: PlanSourceKind = PlanSourceKind.MANUAL
    provider_name: ProviderName | None = None
    model_name: ModelName | None = None

    def model_post_init(self, __context: Any) -> None:
        has_model_identity = (
            self.provider_name is not None and self.model_name is not None
        )
        if self.source_kind is PlanSourceKind.MODEL and not has_model_identity:
            raise ValueError("MODEL source requires provider_name and model_name")
        if self.source_kind is not PlanSourceKind.MODEL and (
            self.provider_name is not None or self.model_name is not None
        ):
            raise ValueError("provider_name and model_name require MODEL source")


class PlanReject(BaseModel):
    reason: RejectReason


class LearningPlanResponse(BaseModel):
    id: int
    project_id: int
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlanVersionResponse(BaseModel):
    id: int
    plan_id: int
    version_number: int
    status: PlanVersionStatus
    goal: str
    content: dict[str, Any]
    source_kind: PlanSourceKind
    provider_name: str | None
    model_name: str | None
    created_at: datetime
    published_at: datetime | None
    confirmed_by_user_id: int | None
    rejection_reason: str | None
    is_current: bool

    model_config = ConfigDict(from_attributes=True)
