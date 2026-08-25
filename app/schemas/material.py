from datetime import datetime

from pydantic import BaseModel

from app.models.material import MaterialFormat, ParseStatus


class MaterialUploadResponse(BaseModel):
    material_id: int
    version_id: int
    name: str
    description: str | None
    enabled: bool
    version_number: int
    original_filename: str
    normalized_format: MaterialFormat
    mime_type: str
    size_bytes: int
    content_hash: str
    parse_status: ParseStatus
    uploaded_at: datetime
