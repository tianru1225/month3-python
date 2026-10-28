from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.learning_project import LearningProject
from app.models.material import Material, ParseStatus
from app.models.project_material import ProjectMaterialBinding
from app.repositories.material_repository import get_material_for_user
from app.repositories.project_material_repository import create_binding
from app.repositories.project_material_repository import get_active_binding
from app.repositories.project_material_repository import list_active_materials
from app.repositories.project_material_repository import unbind
from app.repositories.project_repository import get_project_by_id_and_user
from app.schemas.project_material import ProjectMaterialResponse
from app.schemas.project_material import ProjectMaterialVersionResponse


def _project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "PROJECT_NOT_FOUND", "message": "project not found"},
    )


def _material_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "MATERIAL_NOT_FOUND", "message": "material not found"},
    )


def _get_owned_project(
    db: Session,
    *,
    project_id: int,
    user_id: int,
) -> LearningProject:
    project = get_project_by_id_and_user(
        db,
        project_id=project_id,
        user_id=user_id,
    )
    if project is None:
        raise _project_not_found()
    return project


def _get_owned_material(
    db: Session,
    *,
    material_id: int,
    user_id: int,
) -> Material:
    material = get_material_for_user(
        db,
        material_id=material_id,
        user_id=user_id,
    )
    if material is None:
        raise _material_not_found()
    return material


def bind_material_or_raise(
    db: Session,
    *,
    project_id: int,
    material_id: int,
    user_id: int,
) -> tuple[ProjectMaterialBinding, bool]:
    _get_owned_project(db, project_id=project_id, user_id=user_id)
    _get_owned_material(db, material_id=material_id, user_id=user_id)

    existing = get_active_binding(
        db,
        project_id=project_id,
        material_id=material_id,
    )
    if existing is not None:
        return existing, False

    return (
        create_binding(
            db,
            project_id=project_id,
            material_id=material_id,
        ),
        True,
    )


def list_project_materials_or_raise(
    db: Session,
    *,
    project_id: int,
    user_id: int,
) -> list[ProjectMaterialResponse]:
    _get_owned_project(db, project_id=project_id, user_id=user_id)
    items = []
    for binding, material, version in list_active_materials(
        db, project_id=project_id, user_id=user_id
    ):
        latest_version = None
        if version is not None:
            latest_version = ProjectMaterialVersionResponse(
                version_id=version.id,
                version_number=version.version_number,
                original_filename=version.original_filename,
                parse_status=ParseStatus(version.parse_status),
                parse_error_code=version.parse_error_code,
                parse_error_message=version.parse_error_message,
            )
        items.append(
            ProjectMaterialResponse(
                id=binding.id,
                project_id=binding.project_id,
                material_id=binding.material_id,
                bound_at=binding.bound_at,
                unbound_at=binding.unbound_at,
                name=material.name,
                latest_version=latest_version,
            )
        )
    return items


def unbind_material_or_raise(
    db: Session,
    *,
    project_id: int,
    material_id: int,
    user_id: int,
) -> None:
    _get_owned_project(db, project_id=project_id, user_id=user_id)
    _get_owned_material(db, material_id=material_id, user_id=user_id)

    binding = get_active_binding(
        db,
        project_id=project_id,
        material_id=material_id,
    )
    if binding is not None:
        unbind(db, binding, unbound_at=datetime.now(timezone.utc))