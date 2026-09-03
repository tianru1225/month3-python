from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evaluation import Evaluation, EvaluationDecision
from app.models.evidence import Evidence
from app.models.learning_plan import PlanVersion, PlanVersionStatus
from app.models.learning_task import LearningTask, TaskStatus
from app.repositories.evaluation_repository import (
    add_evaluation,
    get_by_evidence_id,
    get_by_id,
    get_latest_evidence_for_task,
    get_owned_evidence_context,
    set_final_decision,
    set_human_decision,
    set_model_suggestion,
)
from app.schemas.evaluation import (
    HumanDecisionCreate,
    ModelSuggestionCreate,
    RuleEvaluationCreate,
)
from app.services.learning_task_service import transition_task_status


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _get_owned_evidence_or_raise(
    db: Session,
    *,
    evidence_id: int,
    user_id: int,
) -> tuple[Evidence, LearningTask, PlanVersion]:
    context = get_owned_evidence_context(
        db,
        evidence_id=evidence_id,
        user_id=user_id,
    )
    if context is None:
        raise _error(
            "EVIDENCE_NOT_FOUND",
            "evidence not found",
            status.HTTP_404_NOT_FOUND,
        )

    return context


def _require_active_submitted_latest(
    db: Session,
    *,
    evidence: Evidence,
    task: LearningTask,
    version: PlanVersion,
) -> None:
    if version.status != PlanVersionStatus.PUBLISHED.value or not version.is_current:
        raise _error(
            "PLAN_VERSION_NOT_ACTIVE",
            "evaluation requires the current published plan version",
            status.HTTP_409_CONFLICT,
        )
    if task.status != TaskStatus.SUBMITTED.value:
        raise _error(
            "EVIDENCE_NOT_SUBMITTED",
            "task must be submitted before evaluation",
            status.HTTP_409_CONFLICT,
        )

    latest = get_latest_evidence_for_task(db, task_id=task.id)
    if latest is None or latest.id != evidence.id:
        raise _error(
            "EVIDENCE_NOT_LATEST",
            "only the latest evidence attempt can be evaluated",
            status.HTTP_409_CONFLICT,
        )


def _get_owned_evaluation_or_raise(
    db: Session,
    *,
    evaluation_id: int,
    user_id: int,
) -> tuple[Evaluation, Evidence, LearningTask, PlanVersion]:
    evaluation = get_by_id(db, evaluation_id=evaluation_id)
    if evaluation is None:
        raise _error(
            "EVALUATION_NOT_FOUND",
            "evaluation not found",
            status.HTTP_404_NOT_FOUND,
        )
    context = get_owned_evidence_context(
        db,
        evidence_id=evaluation.evidence_id,
        user_id=user_id,
    )
    if context is None:
        raise _error(
            "EVALUATION_NOT_FOUND",
            "evaluation not found",
            status.HTTP_404_NOT_FOUND,
        )
    evidence, task, version = context
    return evaluation, evidence, task, version


def create_evaluation(
    db: Session,
    *,
    evidence_id: int,
    user_id: int,
    payload: RuleEvaluationCreate,
) -> Evaluation:
    if payload.evidence_id != evidence_id:
        raise _error(
            "EVIDENCE_ID_MISMATCH",
            "payload evidence_id does not match the requested evidence",
            status.HTTP_400_BAD_REQUEST,
        )
    if not payload.rule_result:
        raise _error(
            "RULE_RESULT_REQUIRED",
            "rule_result must not be empty",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    evidence, task, version = _get_owned_evidence_or_raise(
        db,
        evidence_id=evidence_id,
        user_id=user_id,
    )
    if get_by_evidence_id(db, evidence_id=evidence_id) is not None:
        raise _error(
            "EVALUATION_ALREADY_EXISTS",
            "evidence already has an evaluation",
            status.HTTP_409_CONFLICT,
        )
    _require_active_submitted_latest(
        db,
        evidence=evidence,
        task=task,
        version=version,
    )

    try:
        evaluation = add_evaluation(
            db,
            evidence_id=evidence_id,
            rule_status=payload.rule_status.value,
            rule_result=payload.rule_result,
        )
        db.commit()
        db.refresh(evaluation)
        return evaluation
    except IntegrityError as exc:
        db.rollback()
        if get_by_evidence_id(db, evidence_id=evidence_id) is not None:
            raise _error(
                "EVALUATION_ALREADY_EXISTS",
                "evidence already has an evaluation",
                status.HTTP_409_CONFLICT,
            ) from exc
        raise
    except Exception:
        db.rollback()
        raise


def record_model_suggestion(
    db: Session,
    *,
    evaluation_id: int,
    user_id: int,
    payload: ModelSuggestionCreate,
) -> Evaluation:
    evaluation, evidence, task, version = _get_owned_evaluation_or_raise(
        db,
        evaluation_id=evaluation_id,
        user_id=user_id,
    )
    if evaluation.final_decision is not None:
        raise _error(
            "MODEL_SUGGESTION_FINALIZED",
            "model suggestion cannot change after finalization",
            status.HTTP_409_CONFLICT,
        )
    _require_active_submitted_latest(
        db,
        evidence=evidence,
        task=task,
        version=version,
    )

    suggestion = payload.model_dump(mode="json")
    try:
        evaluation = set_model_suggestion(
            db,
            evaluation,
            suggestion=suggestion,
        )
        db.commit()
        db.refresh(evaluation)
        return evaluation
    except Exception:
        db.rollback()
        raise


def confirm_evaluation(
    db: Session,
    *,
    evaluation_id: int,
    user_id: int,
    payload: HumanDecisionCreate,
) -> Evaluation:
    evaluation, evidence, task, version = _get_owned_evaluation_or_raise(
        db,
        evaluation_id=evaluation_id,
        user_id=user_id,
    )
    if evaluation.final_decision is not None:
        raise _error(
            "EVALUATION_ALREADY_FINALIZED",
            "finalized evaluation cannot be confirmed again",
            status.HTTP_409_CONFLICT,
        )
    _require_active_submitted_latest(
        db,
        evidence=evidence,
        task=task,
        version=version,
    )

    try:
        evaluation = set_human_decision(
            db,
            evaluation,
            decision=payload.decision.value,
            note=payload.note,
            user_id=user_id,
            confirmed_at=utc_now(),
        )
        db.commit()
        db.refresh(evaluation)
        return evaluation
    except Exception:
        db.rollback()
        raise


def finalize_evaluation(
    db: Session,
    *,
    evaluation_id: int,
    user_id: int,
) -> Evaluation:
    evaluation, evidence, task, version = _get_owned_evaluation_or_raise(
        db,
        evaluation_id=evaluation_id,
        user_id=user_id,
    )
    if evaluation.final_decision is not None:
        raise _error(
            "EVALUATION_ALREADY_FINALIZED",
            "evaluation has already been finalized",
            status.HTTP_409_CONFLICT,
        )
    _require_active_submitted_latest(
        db,
        evidence=evidence,
        task=task,
        version=version,
    )
    if evaluation.human_decision is None:
        raise _error(
            "HUMAN_DECISION_REQUIRED",
            "human decision is required before finalization",
            status.HTTP_409_CONFLICT,
        )

    try:
        decision = EvaluationDecision(evaluation.human_decision)
        target_status = TaskStatus(decision.value)
        set_final_decision(
            db,
            evaluation,
            decision=decision.value,
            user_id=user_id,
            finalized_at=utc_now(),
        )
        transition_task_status(
            db,
            plan_version_id=task.plan_version_id,
            task_id=task.id,
            user_id=user_id,
            target_status=target_status,
            commit=False,
        )
        db.commit()
        db.refresh(evaluation)
        return evaluation
    except HTTPException as exc:
        db.rollback()
        raise _error(
            "EVALUATION_FINALIZE_CONFLICT",
            str(exc.detail),
            status.HTTP_409_CONFLICT,
        ) from exc
    except Exception:
        db.rollback()
        raise


def get_evaluation(
    db: Session,
    *,
    evaluation_id: int,
    user_id: int,
) -> Evaluation:
    evaluation = get_by_id(db, evaluation_id=evaluation_id)
    if evaluation is None:
        raise _error(
            "EVALUATION_NOT_FOUND",
            "evaluation not found",
            status.HTTP_404_NOT_FOUND,
        )
    if (
        get_owned_evidence_context(
            db,
            evidence_id=evaluation.evidence_id,
            user_id=user_id,
        )
        is None
    ):
        raise _error(
            "EVALUATION_NOT_FOUND",
            "evaluation not found",
            status.HTTP_404_NOT_FOUND,
        )
    return evaluation
