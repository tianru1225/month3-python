from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.deps.auth import get_current_user
from app.deps.db import get_db
from app.models.user import User
from app.schemas.knowledge import KnowledgeNodeCreate
from app.schemas.knowledge import KnowledgeNodePrerequisiteResponse
from app.schemas.knowledge import KnowledgeNodeResponse
from app.schemas.knowledge import KnowledgeNodeSourceCreate
from app.schemas.knowledge import KnowledgeNodeSourceResponse
from app.services.knowledge_service import add_prerequisite_or_raise
from app.services.knowledge_service import add_source_or_raise
from app.services.knowledge_service import create_knowledge_node_or_raise
from app.services.knowledge_service import delete_prerequisite_or_raise
from app.services.knowledge_service import get_knowledge_node_or_raise
from app.services.knowledge_service import list_knowledge_nodes_or_raise

router = APIRouter(prefix="/projects", tags=["knowledge-nodes"])


@router.post(
    "/{project_id}/knowledge-nodes",
    response_model=KnowledgeNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_node(
    project_id: int,
    payload: KnowledgeNodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeNodeResponse:
    return create_knowledge_node_or_raise(
        db, project_id=project_id, user_id=current_user.id, payload=payload
    )


@router.get(
    "/{project_id}/knowledge-nodes",
    response_model=list[KnowledgeNodeResponse],
)
def list_nodes(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[KnowledgeNodeResponse]:
    return list_knowledge_nodes_or_raise(
        db, project_id=project_id, user_id=current_user.id
    )


@router.get(
    "/{project_id}/knowledge-nodes/{node_id}",
    response_model=KnowledgeNodeResponse,
)
def get_node(
    project_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeNodeResponse:
    return get_knowledge_node_or_raise(
        db,
        project_id=project_id,
        node_id=node_id,
        user_id=current_user.id,
    )


@router.post(
    "/{project_id}/knowledge-nodes/{node_id}/prerequisites/{prerequisite_node_id}",
    response_model=KnowledgeNodePrerequisiteResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_prerequisite(
    project_id: int,
    node_id: int,
    prerequisite_node_id: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeNodePrerequisiteResponse:
    edge, created = add_prerequisite_or_raise(
        db,
        project_id=project_id,
        node_id=node_id,
        prerequisite_node_id=prerequisite_node_id,
        user_id=current_user.id,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return edge


@router.delete(
    "/{project_id}/knowledge-nodes/{node_id}/prerequisites/{prerequisite_node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_prerequisite(
    project_id: int,
    node_id: int,
    prerequisite_node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    delete_prerequisite_or_raise(
        db,
        project_id=project_id,
        node_id=node_id,
        prerequisite_node_id=prerequisite_node_id,
        user_id=current_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_id}/knowledge-nodes/{node_id}/sources",
    response_model=KnowledgeNodeSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_source(
    project_id: int,
    node_id: int,
    payload: KnowledgeNodeSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeNodeSourceResponse:
    return add_source_or_raise(
        db,
        project_id=project_id,
        node_id=node_id,
        user_id=current_user.id,
        payload=payload,
    )
