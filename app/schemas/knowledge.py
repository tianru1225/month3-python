from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class KnowledgeNodeCreate(BaseModel):
    title: Title
    description: Description
    difficulty: int = Field(default=1, ge=1, le=5)


class KnowledgeNodeSourceCreate(BaseModel):
    material_version_id: int = Field(gt=0)
    block_index: int = Field(ge=0)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    section_path: list[str] = Field(max_length=20)
    quote: str | None = Field(default=None, max_length=2000)


class KnowledgeNodeSourceResponse(BaseModel):
    id: int
    node_id: int
    material_version_id: int
    block_index: int
    line_start: int
    line_end: int
    section_path: list[str]
    quote: str | None
    quote_hash: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeNodeResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    difficulty: int
    status: str
    created_at: datetime
    updated_at: datetime
    prerequisite_node_ids: list[int]
    sources: list[KnowledgeNodeSourceResponse]


class KnowledgeNodePrerequisiteResponse(BaseModel):
    id: int
    node_id: int
    prerequisite_node_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
