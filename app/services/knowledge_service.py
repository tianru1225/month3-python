import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeNode
from app.repositories.knowledge_repository import create_edge
from app.repositories.knowledge_repository import create_node
from app.repositories.knowledge_repository import create_source
from app.repositories.knowledge_repository import delete_edge
from app.repositories.knowledge_repository import get_edge
from app.repositories.knowledge_repository import get_node
from app.repositories.knowledge_repository import get_owned_project
from app.repositories.knowledge_repository import get_ready_version_for_project
from app.repositories.knowledge_repository import list_nodes
from app.repositories.knowledge_repository import list_project_edges
from app.repositories.knowledge_repository import list_sources
from app.schemas.knowledge import KnowledgeNodeCreate
from app.schemas.knowledge import KnowledgeNodePrerequisiteResponse
from app.schemas.knowledge import KnowledgeNodeResponse
from app.schemas.knowledge import KnowledgeNodeSourceCreate
from app.schemas.knowledge import KnowledgeNodeSourceResponse

MATERIAL_STORAGE_DIR = Path("data/materials")


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _project_or_raise(db: Session, *, project_id: int, user_id: int) -> None:
    if get_owned_project(db, project_id=project_id, user_id=user_id) is None:
        raise _error(
            "PROJECT_NOT_FOUND", "project not found", status.HTTP_404_NOT_FOUND
        )


def _node_or_raise(db: Session, *, project_id: int, node_id: int) -> KnowledgeNode:
    node = get_node(db, project_id=project_id, node_id=node_id)
    if node is None:
        raise _error(
            "KNOWLEDGE_NODE_NOT_FOUND",
            "knowledge node not found",
            status.HTTP_404_NOT_FOUND,
        )
    return node


def _response(
    db: Session, *, project_id: int, node: KnowledgeNode
) -> KnowledgeNodeResponse:
    edges = [
        edge
        for edge in list_project_edges(db, project_id=project_id)
        if edge.node_id == node.id
    ]
    return KnowledgeNodeResponse(
        id=node.id,
        project_id=node.project_id,
        title=node.title,
        description=node.description,
        difficulty=node.difficulty,
        status=node.status,
        created_at=node.created_at,
        updated_at=node.updated_at,
        prerequisite_node_ids=[edge.prerequisite_node_id for edge in edges],
        sources=[
            KnowledgeNodeSourceResponse.model_validate(source)
            for source in list_sources(db, node_id=node.id)
        ],
    )


def create_knowledge_node_or_raise(
    db: Session,
    *,
    project_id: int,
    user_id: int,
    payload: KnowledgeNodeCreate,
) -> KnowledgeNodeResponse:
    _project_or_raise(db, project_id=project_id, user_id=user_id)
    node = create_node(
        db,
        project_id=project_id,
        title=payload.title,
        description=payload.description,
        difficulty=payload.difficulty,
    )
    return _response(db, project_id=project_id, node=node)


def list_knowledge_nodes_or_raise(
    db: Session, *, project_id: int, user_id: int
) -> list[KnowledgeNodeResponse]:
    _project_or_raise(db, project_id=project_id, user_id=user_id)
    return [
        _response(db, project_id=project_id, node=node)
        for node in list_nodes(db, project_id=project_id)
    ]


def get_knowledge_node_or_raise(
    db: Session, *, project_id: int, node_id: int, user_id: int
) -> KnowledgeNodeResponse:
    _project_or_raise(db, project_id=project_id, user_id=user_id)
    return _response(
        db,
        project_id=project_id,
        node=_node_or_raise(db, project_id=project_id, node_id=node_id),
    )


def _would_create_cycle(
    db: Session,
    *,
    project_id: int,
    node_id: int,
    prerequisite_node_id: int,
) -> bool:
    adjacency: dict[int, set[int]] = {}
    for edge in list_project_edges(db, project_id=project_id):
        adjacency.setdefault(edge.node_id, set()).add(edge.prerequisite_node_id)

    pending = [prerequisite_node_id]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if current == node_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency.get(current, set()))
    return False


def add_prerequisite_or_raise(
    db: Session,
    *,
    project_id: int,
    node_id: int,
    prerequisite_node_id: int,
    user_id: int,
) -> tuple[KnowledgeNodePrerequisiteResponse, bool]:
    _project_or_raise(db, project_id=project_id, user_id=user_id)
    _node_or_raise(db, project_id=project_id, node_id=node_id)
    _node_or_raise(db, project_id=project_id, node_id=prerequisite_node_id)
    if node_id == prerequisite_node_id:
        raise _error(
            "KNOWLEDGE_PREREQUISITE_INVALID",
            "a knowledge node cannot require itself",
            status.HTTP_400_BAD_REQUEST,
        )

    existing = get_edge(
        db,
        node_id=node_id,
        prerequisite_node_id=prerequisite_node_id,
    )
    if existing is not None:
        return KnowledgeNodePrerequisiteResponse.model_validate(existing), False
    if _would_create_cycle(
        db,
        project_id=project_id,
        node_id=node_id,
        prerequisite_node_id=prerequisite_node_id,
    ):
        raise _error(
            "KNOWLEDGE_PREREQUISITE_CYCLE",
            "prerequisite relationship would create a cycle",
            status.HTTP_409_CONFLICT,
        )
    edge = create_edge(
        db,
        node_id=node_id,
        prerequisite_node_id=prerequisite_node_id,
    )
    return KnowledgeNodePrerequisiteResponse.model_validate(edge), True


def delete_prerequisite_or_raise(
    db: Session,
    *,
    project_id: int,
    node_id: int,
    prerequisite_node_id: int,
    user_id: int,
) -> None:
    _project_or_raise(db, project_id=project_id, user_id=user_id)
    _node_or_raise(db, project_id=project_id, node_id=node_id)
    _node_or_raise(db, project_id=project_id, node_id=prerequisite_node_id)
    edge = get_edge(
        db,
        node_id=node_id,
        prerequisite_node_id=prerequisite_node_id,
    )
    if edge is not None:
        delete_edge(db, edge)


def _source_block(
    version: Any, payload: KnowledgeNodeSourceCreate
) -> tuple[str | None, str | None]:
    metadata = version.source_metadata or {}
    relative_path = metadata.get("sources_path")
    if not isinstance(relative_path, str):
        raise _error(
            "KNOWLEDGE_SOURCE_INVALID",
            "source metadata is incomplete",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    root = MATERIAL_STORAGE_DIR.resolve()
    source_path = (MATERIAL_STORAGE_DIR / relative_path).resolve()
    if root != source_path and root not in source_path.parents:
        raise _error(
            "KNOWLEDGE_SOURCE_INVALID",
            "source path is invalid",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        source_map = json.loads(source_path.read_text(encoding="utf-8"))
        if source_map.get("material_version_id") != version.id:
            raise ValueError("version mismatch")
        block = source_map["blocks"][payload.block_index]
        source = block["source"]
        if (
            source["line_start"] != payload.line_start
            or source["line_end"] != payload.line_end
            or source["section_path"] != payload.section_path
        ):
            raise ValueError("location mismatch")
    except (OSError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise _error(
            "KNOWLEDGE_SOURCE_INVALID",
            "source location does not match parsed Markdown",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc

    quote = payload.quote.strip() if payload.quote is not None else None
    if quote == "":
        raise _error(
            "KNOWLEDGE_SOURCE_INVALID",
            "quote must not be empty",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if quote is not None and quote not in block.get("text", ""):
        raise _error(
            "KNOWLEDGE_SOURCE_INVALID",
            "quote is not contained in source block",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return quote, sha256(quote.encode()).hexdigest() if quote else None


def add_source_or_raise(
    db: Session,
    *,
    project_id: int,
    node_id: int,
    user_id: int,
    payload: KnowledgeNodeSourceCreate,
) -> KnowledgeNodeSourceResponse:
    _project_or_raise(db, project_id=project_id, user_id=user_id)
    _node_or_raise(db, project_id=project_id, node_id=node_id)
    version = get_ready_version_for_project(
        db,
        project_id=project_id,
        user_id=user_id,
        material_version_id=payload.material_version_id,
    )
    if version is None:
        raise _error(
            "KNOWLEDGE_SOURCE_INVALID",
            "source must be a READY Markdown version bound to this project",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    quote, quote_hash = _source_block(version, payload)
    source = create_source(
        db,
        node_id=node_id,
        material_version_id=version.id,
        block_index=payload.block_index,
        line_start=payload.line_start,
        line_end=payload.line_end,
        section_path=payload.section_path,
        quote=quote,
        quote_hash=quote_hash,
    )
    return KnowledgeNodeSourceResponse.model_validate(source)
