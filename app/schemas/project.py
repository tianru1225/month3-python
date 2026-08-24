from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
ProjectGoal = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]
CurrentLevel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]
ExpectedOutcome = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class ProjectCreate(BaseModel):
    name: ProjectName
    goal: ProjectGoal
    current_level: CurrentLevel
    deadline: date | None = None
    daily_minutes: int = Field(default=60, ge=1, le=1440)
    weekly_days: int = Field(default=7, ge=1, le=7)
    expected_outcome: ExpectedOutcome | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    goal: str
    current_level: str
    deadline: date | None
    daily_minutes: int
    weekly_days: int
    expected_outcome: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
