from datetime import datetime

from pydantic import BaseModel

from app.models.material import MaterialFormat, ParseStatus


class MaterialUploadResponse(BaseModel):
    material_id: int
    name: str
    description: str | None
    original_filename: str
    normalized_format: MaterialFormat
    mime_type: str
    size_bytes: int
    content_hash: str
    parse_status: ParseStatus
    uploaded_at: datetime


class MaterialParseJobResponse(BaseModel):
    material_id: int
    job_id: str | None
    parse_status: ParseStatus


class MaterialParseResponse(BaseModel):
    material_id: int
    original_filename: str
    normalized_format: MaterialFormat
    parse_status: ParseStatus
    parse_job_id: str | None
    parser_name: str | None
    parser_version: str | None
    content_summary: str | None
    parsed_content_location: str | None
    source_metadata: dict | None
    parse_error_code: str | None
    parse_error_message: str | None
    processed_at: datetime | None