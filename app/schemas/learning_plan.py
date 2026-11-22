from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ProviderName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
ModelName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
]


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: dict[str, Any] = Field(default_factory=dict)
    provider_name: ProviderName | None = None
    model_name: ModelName | None = None

    def model_post_init(self, __context: Any) -> None:
        if (self.provider_name is None) != (self.model_name is None):
            raise ValueError("provider_name and model_name must be provided together")


class LearningPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    content: dict[str, Any]
    provider_name: str | None
    model_name: str | None
    created_at: datetime
    updated_at: datetime
    locked_at: datetime | None