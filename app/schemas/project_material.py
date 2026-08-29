from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectMaterialBindingResponse(BaseModel):
    id: int
    project_id: int
    material_id: int
    bound_at: datetime
    unbound_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
