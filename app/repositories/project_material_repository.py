from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_project import LearningProject
from app.models.material import Material, MaterialVersion, ParseStatus
from app.models.project_material import ProjectMaterialBinding


def get_active_binding(
    db: Session,
    *,
    project_id: int,
    material_id: int,
) -> ProjectMaterialBinding | None:
    return db.scalar(
        select(ProjectMaterialBinding).where(
            ProjectMaterialBinding.project_id == project_id,
            ProjectMaterialBinding.material_id == material_id,
            ProjectMaterialBinding.unbound_at.is_(None),
        )
    )


def list_active_bindings(
    db: Session,
    *,
    project_id: int,
) -> list[ProjectMaterialBinding]:
    statement = (
        select(ProjectMaterialBinding)
        .where(
            ProjectMaterialBinding.project_id == project_id,
            ProjectMaterialBinding.unbound_at.is_(None),
        )
        .order_by(
            ProjectMaterialBinding.bound_at.asc(),
            ProjectMaterialBinding.id.asc(),
        )
    )
    return list(db.scalars(statement))


def create_binding(
    db: Session,
    *,
    project_id: int,
    material_id: int,
) -> ProjectMaterialBinding:
    binding = ProjectMaterialBinding(
        project_id=project_id,
        material_id=material_id,
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


def unbind(
    db: Session,
    binding: ProjectMaterialBinding,
    *,
    unbound_at: datetime,
) -> None:
    binding.unbound_at = unbound_at
    db.commit()


def list_ready_versions_for_project(
    db: Session,
    *,
    project_id: int,
    user_id: int,
) -> list[MaterialVersion]:
    statement = (
        select(MaterialVersion)
        .join(Material, Material.id == MaterialVersion.material_id)
        .join(
            ProjectMaterialBinding,
            ProjectMaterialBinding.material_id == Material.id,
        )
        .join(LearningProject, LearningProject.id == ProjectMaterialBinding.project_id)
        .where(
            LearningProject.id == project_id,
            LearningProject.user_id == user_id,
            Material.user_id == user_id,
            ProjectMaterialBinding.unbound_at.is_(None),
            MaterialVersion.parse_status == ParseStatus.READY.value,
        )
        .order_by(MaterialVersion.id)
    )
    return list(db.scalars(statement))
