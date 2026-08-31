from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge import (
    KnowledgeNode,
    KnowledgeNodePrerequisite,
    KnowledgeNodeSource,
)
from app.models.learning_project import LearningProject
from app.models.material import Material, MaterialVersion, ParseStatus
from app.models.project_material import ProjectMaterialBinding


def get_owned_project(
    db: Session, *, project_id: int, user_id: int
) -> LearningProject | None:
    return db.scalar(
        select(LearningProject).where(
            LearningProject.id == project_id,
            LearningProject.user_id == user_id,
        )
    )


def get_node(db: Session, *, project_id: int, node_id: int) -> KnowledgeNode | None:
    return db.scalar(
        select(KnowledgeNode).where(
            KnowledgeNode.id == node_id,
            KnowledgeNode.project_id == project_id,
        )
    )


def list_nodes(db: Session, *, project_id: int) -> list[KnowledgeNode]:
    return list(
        db.scalars(
            select(KnowledgeNode)
            .where(KnowledgeNode.project_id == project_id)
            .order_by(KnowledgeNode.id.asc())
        )
    )


def create_node(
    db: Session,
    *,
    project_id: int,
    title: str,
    description: str,
    difficulty: int,
) -> KnowledgeNode:
    node = KnowledgeNode(
        project_id=project_id,
        title=title,
        description=description,
        difficulty=difficulty,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def list_project_edges(
    db: Session, *, project_id: int
) -> list[KnowledgeNodePrerequisite]:
    return list(
        db.scalars(
            select(KnowledgeNodePrerequisite)
            .join(KnowledgeNode, KnowledgeNode.id == KnowledgeNodePrerequisite.node_id)
            .where(KnowledgeNode.project_id == project_id)
            .order_by(KnowledgeNodePrerequisite.id.asc())
        )
    )


def get_edge(
    db: Session, *, node_id: int, prerequisite_node_id: int
) -> KnowledgeNodePrerequisite | None:
    return db.scalar(
        select(KnowledgeNodePrerequisite).where(
            KnowledgeNodePrerequisite.node_id == node_id,
            KnowledgeNodePrerequisite.prerequisite_node_id == prerequisite_node_id,
        )
    )


def create_edge(
    db: Session, *, node_id: int, prerequisite_node_id: int
) -> KnowledgeNodePrerequisite:
    edge = KnowledgeNodePrerequisite(
        node_id=node_id,
        prerequisite_node_id=prerequisite_node_id,
    )
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return edge


def delete_edge(db: Session, edge: KnowledgeNodePrerequisite) -> None:
    db.delete(edge)
    db.commit()


def get_ready_version_for_project(
    db: Session,
    *,
    project_id: int,
    user_id: int,
    material_version_id: int,
) -> MaterialVersion | None:
    return db.scalar(
        select(MaterialVersion)
        .join(Material, Material.id == MaterialVersion.material_id)
        .join(
            ProjectMaterialBinding,
            ProjectMaterialBinding.material_id == Material.id,
        )
        .where(
            MaterialVersion.id == material_version_id,
            MaterialVersion.parse_status == ParseStatus.READY.value,
            MaterialVersion.normalized_format == "markdown",
            ProjectMaterialBinding.project_id == project_id,
            ProjectMaterialBinding.unbound_at.is_(None),
            Material.user_id == user_id,
        )
    )


def create_source(
    db: Session,
    *,
    node_id: int,
    material_version_id: int,
    block_index: int,
    line_start: int,
    line_end: int,
    section_path: list[str],
    quote: str | None,
    quote_hash: str | None,
) -> KnowledgeNodeSource:
    source = KnowledgeNodeSource(
        node_id=node_id,
        material_version_id=material_version_id,
        block_index=block_index,
        line_start=line_start,
        line_end=line_end,
        section_path=section_path,
        quote=quote,
        quote_hash=quote_hash,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def list_sources(db: Session, *, node_id: int) -> list[KnowledgeNodeSource]:
    return list(
        db.scalars(
            select(KnowledgeNodeSource)
            .where(KnowledgeNodeSource.node_id == node_id)
            .order_by(KnowledgeNodeSource.id.asc())
        )
    )
