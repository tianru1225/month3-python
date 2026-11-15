from datetime import datetime

from pydantic import BaseModel


class MaterialManagementItem(BaseModel):
    material_id: int
    name: str
    created_at: datetime
    deletion_pending: bool
    blockers: list[str]


class MaterialManagementPage(BaseModel):
    items: list[MaterialManagementItem]
    next_before_id: int | None