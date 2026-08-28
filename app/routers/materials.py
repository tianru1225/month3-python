from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.deps.auth import get_current_user
from app.deps.db import get_db
from app.models.user import User
from app.schemas.material import MaterialUploadResponse, MaterialParseResponse
from app.services.material_service import (
    MATERIAL_MAX_UPLOAD_BYTES,
    upload_material_or_raise,
    parse_material_version_or_raise,
)

router = APIRouter(prefix="/materials", tags=["materials"])


@router.post(
    "",
    response_model=MaterialUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传学习资料",
)
async def upload_material(
    name: Annotated[str, Form(min_length=1, max_length=120)],
    file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form(max_length=5000)] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MaterialUploadResponse:
    try:
        content = await file.read(MATERIAL_MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    return upload_material_or_raise(
        db,
        user_id=current_user.id,
        name=name,
        description=description,
        filename=file.filename or "",
        content_type=file.content_type or "",
        content=content,
    )


@router.post(
    "/{material_id}/versions/{version_id}/parse",
    response_model=MaterialParseResponse,
    status_code=status.HTTP_200_OK,
    summary="解析Markdown资料",
)
def parse_material(
    material_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MaterialParseResponse:
    return parse_material_version_or_raise(
        db,
        user_id=current_user.id,
        material_id=material_id,
        version_id=version_id,
    )
