from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class ProjectCreate(BaseModel):
    name: ProjectName

    model_config = ConfigDict(extra="forbid")


class ProjectResponse(BaseModel):
    id: int
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)