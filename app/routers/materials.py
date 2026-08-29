from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.deps.auth import get_current_user
from app.deps.db import get_db
from app.models.user import User
from app.schemas.material import MaterialParseJobResponse
from app.schemas.material import MaterialParseResponse
from app.schemas.material import MaterialUploadResponse
from app.services.material_service import MATERIAL_MAX_UPLOAD_BYTES
from app.services.material_service import enqueue_material_parse_or_raise
from app.services.material_service import get_material_parse_status_or_raise
from app.services.material_service import upload_material_or_raise

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
    response_model=MaterialParseJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="投递 Markdown 解析任务",
)
def enqueue_material_parse(
    material_id: int,
    version_id: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MaterialParseJobResponse:
    result, created = enqueue_material_parse_or_raise(
        db,
        user_id=current_user.id,
        material_id=material_id,
        version_id=version_id,
    )
    response.status_code = status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
    return result


@router.get(
    "/{material_id}/versions/{version_id}/parse",
    response_model=MaterialParseResponse,
    summary="查询 Markdown 解析状态",
)
def get_material_parse_status(
    material_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MaterialParseResponse:
    return get_material_parse_status_or_raise(
        db,
        user_id=current_user.id,
        material_id=material_id,
        version_id=version_id,
    )
