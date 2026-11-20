from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_project import LearningProject
from app.models.material import Material, ParseStatus
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


def list_active_materials(
    db: Session,
    *,
    project_id: int,
    user_id: int,
) -> list[tuple[ProjectMaterialBinding, Material]]:
    # 资料本身保存解析状态，失败状态也必须返回。
    statement = (
        select(ProjectMaterialBinding, Material)
        .join(Material, Material.id == ProjectMaterialBinding.material_id)
        .where(
            ProjectMaterialBinding.project_id == project_id,
            ProjectMaterialBinding.unbound_at.is_(None),
            Material.user_id == user_id,
            Material.deletion_started_at.is_(None),
        )
        .order_by(
            ProjectMaterialBinding.bound_at.asc(),
            ProjectMaterialBinding.id.asc(),
        )
    )
    return [
        (binding, material)
        for binding, material in db.execute(statement)
    ]


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


def list_ready_materials_for_project(
    db: Session,
    *,
    project_id: int,
    user_id: int,
) -> list[Material]:
    statement = (
        select(Material)
        .join(
            ProjectMaterialBinding,
            ProjectMaterialBinding.material_id == Material.id,
        )
        .join(LearningProject, LearningProject.id == ProjectMaterialBinding.project_id)
        .where(
            LearningProject.id == project_id,
            LearningProject.user_id == user_id,
            LearningProject.deleted_at.is_(None),
            Material.user_id == user_id,
            Material.deletion_started_at.is_(None),
            ProjectMaterialBinding.unbound_at.is_(None),
            Material.parse_status == ParseStatus.READY.value,
        )
        .order_by(Material.id)
    )
    return list(db.scalars(statement))