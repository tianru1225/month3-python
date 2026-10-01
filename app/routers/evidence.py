from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.deps.auth import get_current_user
from app.deps.db import get_db
from app.models.evidence import EvidenceSourceKind
from app.models.user import User
from app.schemas.evidence import EvidenceCreate, EvidenceResponse, EvidenceSourceContext
from app.schemas.evidence_acceptance import EvidenceAcceptanceResponse
from app.services.evidence_acceptance_service import evaluate_latest_evidence
from app.services.evidence_service import submit_evidence

router = APIRouter(prefix="/plan-versions", tags=["evidence"])


@router.post(
    "/{plan_version_id}/tasks/{task_id}/evidence",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交学习证据",
)
def create_task_evidence(
    plan_version_id: int,
    task_id: int,
    payload: EvidenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceResponse:
    evidence = submit_evidence(
        db,
        plan_version_id=plan_version_id,
        task_id=task_id,
        user_id=current_user.id,
        payload=payload,
        source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
    )
    return EvidenceResponse.model_validate(evidence)


@router.post(
    "/{plan_version_id}/tasks/{task_id}/evaluate",
    response_model=EvidenceAcceptanceResponse,
    summary="按确定性规则验收最新证据",
)
def evaluate_task_evidence(
    plan_version_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceAcceptanceResponse:
    return evaluate_latest_evidence(
        db,
        plan_version_id=plan_version_id,
        task_id=task_id,
        user_id=current_user.id,
    )
