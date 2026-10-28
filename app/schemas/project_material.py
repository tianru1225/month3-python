from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.material import ParseStatus


class ProjectMaterialBindingResponse(BaseModel):
    id: int
    project_id: int
    material_id: int
    bound_at: datetime
    unbound_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ProjectMaterialVersionResponse(BaseModel):
    version_id: int
    version_number: int
    original_filename: str
    parse_status: ParseStatus
    parse_error_code: str | None
    parse_error_message: str | None


class ProjectMaterialResponse(ProjectMaterialBindingResponse):
    name: str
    latest_version: ProjectMaterialVersionResponse | None