from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.deps.auth import get_current_user
from app.deps.db import get_db
from app.models.user import User
from app.schemas.project_material import ProjectMaterialBindingResponse
from app.services.project_material_service import bind_material_or_raise
from app.services.project_material_service import list_project_materials_or_raise
from app.services.project_material_service import unbind_material_or_raise

router = APIRouter(prefix="/projects", tags=["project-materials"])


@router.post(
    "/{project_id}/materials/{material_id}",
    response_model=ProjectMaterialBindingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="绑定项目资料",
)
def bind_material(
    project_id: int,
    material_id: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectMaterialBindingResponse:
    binding, created = bind_material_or_raise(
        db,
        project_id=project_id,
        material_id=material_id,
        user_id=current_user.id,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return ProjectMaterialBindingResponse.model_validate(binding)


@router.get(
    "/{project_id}/materials",
    response_model=list[ProjectMaterialBindingResponse],
    summary="列出项目资料",
)
def list_materials(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectMaterialBindingResponse]:
    return list_project_materials_or_raise(
        db,
        project_id=project_id,
        user_id=current_user.id,
    )


@router.delete(
    "/{project_id}/materials/{material_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="解绑项目资料",
)
def unbind_material(
    project_id: int,
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    unbind_material_or_raise(
        db,
        project_id=project_id,
        material_id=material_id,
        user_id=current_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
