from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evidence import Evidence
from app.models.learning_plan import PlanVersion, PlanVersionStatus
from app.models.learning_task import LearningTask, TaskStatus
from app.repositories.evidence_repository import (
    add_evidence,
    list_task_evidence as repository_list_task_evidence,
    next_attempt_number,
)
from app.repositories.learning_task_repository import (
    get_owned_plan_version,
    get_task,
)
from app.schemas.evidence import (
    EvidenceCreate,
    EvidenceSourceContext,
    TestReportEvidenceCreate,
    TextEvidenceCreate,
)
from app.services.learning_task_service import transition_task_status


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _get_owned_task_or_raise(
    db: Session,
    *,
    plan_version_id: int,
    task_id: int,
    user_id: int,
) -> tuple[PlanVersion, LearningTask]:
    version = get_owned_plan_version(
        db,
        plan_version_id=plan_version_id,
        user_id=user_id,
    )
    if version is None:
        raise _error(
            "PLAN_VERSION_NOT_FOUND",
            "plan version not found",
            status.HTTP_404_NOT_FOUND,
        )
    task = get_task(
        db,
        plan_version_id=plan_version_id,
        task_id=task_id,
    )
    if task is None:
        raise _error(
            "LEARNING_TASK_NOT_FOUND",
            "learning task not found in this plan version",
            status.HTTP_404_NOT_FOUND,
        )
    return version, task


def submit_evidence(
    db: Session,
    *,
    plan_version_id: int,
    task_id: int,
    user_id: int,
    payload: EvidenceCreate,
    source: EvidenceSourceContext,
) -> Evidence:
    version, task = _get_owned_task_or_raise(
        db,
        plan_version_id=plan_version_id,
        task_id=task_id,
        user_id=user_id,
    )
    if version.status != PlanVersionStatus.PUBLISHED.value or not version.is_current:
        raise _error(
            "PLAN_VERSION_NOT_ACTIVE",
            "evidence can only be submitted to the current published plan version",
            status.HTTP_409_CONFLICT,
        )
    if task.status != TaskStatus.IN_PROGRESS.value:
        raise _error(
            "TASK_NOT_ACCEPTING_EVIDENCE",
            "task must be in progress before evidence is submitted",
            status.HTTP_409_CONFLICT,
        )

    text_content: str | None = None
    test_report: dict[str, object] | None = None
    if isinstance(payload, TextEvidenceCreate):
        text_content = payload.text_content
    elif isinstance(payload, TestReportEvidenceCreate):
        test_report = payload.test_report.model_dump(mode="json")
    else:
        raise TypeError("unsupported evidence payload")

    try:
        evidence = add_evidence(
            db,
            plan_version_id=plan_version_id,
            task_id=task.id,
            attempt_number=next_attempt_number(db, task_id=task.id),
            evidence_type=payload.evidence_type.value,
            source_kind=source.kind.value,
            source_ref=source.reference,
            text_content=text_content,
            test_report=test_report,
            submitted_by_user_id=user_id,
        )
    except IntegrityError as exc:
        db.rollback()
        raise _error(
            "EVIDENCE_ATTEMPT_CONFLICT",
            "evidence attempt was submitted concurrently",
            status.HTTP_409_CONFLICT,
        ) from exc

    try:
        transition_task_status(
            db,
            plan_version_id=plan_version_id,
            task_id=task.id,
            user_id=user_id,
            target_status=TaskStatus.SUBMITTED,
        )
        db.refresh(evidence)
        return evidence
    except Exception:
        db.rollback()
        raise


def list_task_evidence(
    db: Session,
    *,
    plan_version_id: int,
    task_id: int,
    user_id: int,
) -> list[Evidence]:
    _, task = _get_owned_task_or_raise(
        db,
        plan_version_id=plan_version_id,
        task_id=task_id,
        user_id=user_id,
    )
    return repository_list_task_evidence(db, task_id=task.id)
