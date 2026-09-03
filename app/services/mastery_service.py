from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evaluation import EvaluationDecision
from app.models.learning_plan import PlanVersionStatus
from app.models.learning_task import TaskStatus
from app.models.mastery import (
    MasteryLevel,
    MasteryRecord,
    ReviewItem,
    ReviewItemStatus,
)
from app.repositories.mastery_repository import (
    add_record,
    create_review_item,
    get_latest_record,
    get_owned_evaluation_context,
    get_owned_review_item,
    get_project_node,
    get_record_by_evaluation_id,
    get_review_item,
    list_due_review_items as repository_list_due_review_items,
    list_project_review_items as repository_list_project_review_items,
    list_records,
    mark_review_completed,
    refresh_review_item,
)
from app.repositories.project_repository import get_project_by_id_and_user


ALGORITHM_VERSION = "mastery-v1"
PASSED_INCREMENT = 20
REVISION_DECREMENT = 10
PASSED_INTERVAL_DAYS = 7
REVISION_INTERVAL_DAYS = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def mastery_level_for_score(score: int) -> MasteryLevel:
    if not 0 <= score <= 100:
        raise ValueError("mastery score must be between 0 and 100")
    if score < 40:
        return MasteryLevel.NOVICE
    if score < 70:
        return MasteryLevel.DEVELOPING
    if score < 90:
        return MasteryLevel.PROFICIENT
    return MasteryLevel.MASTERED


def calculate_mastery(
    *,
    score_before: int,
    decision: EvaluationDecision,
) -> tuple[int, MasteryLevel, int]:
    if not 0 <= score_before <= 100:
        raise ValueError("score_before must be between 0 and 100")

    if decision == EvaluationDecision.PASSED:
        score_after = min(100, score_before + PASSED_INCREMENT)
        interval_days = PASSED_INTERVAL_DAYS
    else:
        score_after = max(0, score_before - REVISION_DECREMENT)
        interval_days = REVISION_INTERVAL_DAYS

    return score_after, mastery_level_for_score(score_after), interval_days


def _existing_result_or_raise(
    db: Session,
    *,
    evaluation_id: int,
    project_id: int,
    knowledge_node_id: int,
) -> tuple[MasteryRecord, ReviewItem, bool] | None:
    record = get_record_by_evaluation_id(
        db,
        evaluation_id=evaluation_id,
    )
    if record is None:
        return None
    if record.project_id != project_id or record.knowledge_node_id != knowledge_node_id:
        raise _error(
            "MASTERY_EVALUATION_NODE_CONFLICT",
            "evaluation is already assigned to another knowledge node",
            status.HTTP_409_CONFLICT,
        )

    item = get_review_item(
        db,
        project_id=project_id,
        knowledge_node_id=knowledge_node_id,
    )
    if item is None:
        raise RuntimeError("mastery record exists without review item")
    return record, item, False


def record_evaluation_mastery(
    db: Session,
    *,
    evaluation_id: int,
    knowledge_node_id: int,
    user_id: int,
) -> tuple[MasteryRecord, ReviewItem, bool]:
    context = get_owned_evaluation_context(
        db,
        evaluation_id=evaluation_id,
        user_id=user_id,
    )
    if context is None:
        raise _error(
            "EVALUATION_NOT_FOUND",
            "evaluation not found",
            status.HTTP_404_NOT_FOUND,
        )

    evaluation, _, task, version, project = context
    if version.status != PlanVersionStatus.PUBLISHED.value or not version.is_current:
        raise _error(
            "PLAN_VERSION_NOT_ACTIVE",
            "mastery requires the current published plan version",
            status.HTTP_409_CONFLICT,
        )
    if evaluation.final_decision is None or evaluation.finalized_at is None:
        raise _error(
            "MASTERY_REQUIRES_FINAL_EVALUATION",
            "evaluation must be finalized before mastery is recorded",
            status.HTTP_409_CONFLICT,
        )

    decision = EvaluationDecision(evaluation.final_decision)
    if task.status != TaskStatus(decision.value).value:
        raise _error(
            "MASTERY_TASK_DECISION_MISMATCH",
            "task status does not match the final evaluation decision",
            status.HTTP_409_CONFLICT,
        )

    node = get_project_node(
        db,
        project_id=project.id,
        knowledge_node_id=knowledge_node_id,
    )
    if node is None:
        raise _error(
            "KNOWLEDGE_NODE_NOT_FOUND",
            "knowledge node not found",
            status.HTTP_404_NOT_FOUND,
        )

    existing = _existing_result_or_raise(
        db,
        evaluation_id=evaluation.id,
        project_id=project.id,
        knowledge_node_id=node.id,
    )
    if existing is not None:
        return existing

    latest = get_latest_record(
        db,
        project_id=project.id,
        knowledge_node_id=node.id,
    )
    finalized_at = _as_utc(evaluation.finalized_at)
    if latest is not None and _as_utc(latest.recorded_at) > finalized_at:
        raise _error(
            "MASTERY_EVENT_OUT_OF_ORDER",
            "an older evaluation cannot replace newer mastery state",
            status.HTTP_409_CONFLICT,
        )

    score_before = latest.score_after if latest is not None else 0
    score_after, level_after, interval_days = calculate_mastery(
        score_before=score_before,
        decision=decision,
    )
    next_review_at = finalized_at + timedelta(days=interval_days)
    calculation: dict[str, object] = {
        "algorithm_version": ALGORITHM_VERSION,
        "decision": decision.value,
        "score_before": score_before,
        "score_after": score_after,
        "delta": score_after - score_before,
        "interval_days": interval_days,
    }
    reason = f"final evaluation decision: {decision.value}"

    try:
        record = add_record(
            db,
            project_id=project.id,
            knowledge_node_id=node.id,
            evaluation_id=evaluation.id,
            score_before=score_before,
            score_after=score_after,
            level_after=level_after.value,
            decision=decision.value,
            interval_days=interval_days,
            next_review_at=next_review_at,
            algorithm_version=ALGORITHM_VERSION,
            calculation=calculation,
            reason=reason,
            recorded_at=finalized_at,
        )
        item = get_review_item(
            db,
            project_id=project.id,
            knowledge_node_id=node.id,
        )
        if item is None:
            item = create_review_item(
                db,
                project_id=project.id,
                knowledge_node_id=node.id,
                last_record_id=record.id,
                mastery_score=score_after,
                mastery_level=level_after.value,
                status=ReviewItemStatus.PENDING.value,
                interval_days=interval_days,
                next_review_at=next_review_at,
            )
        else:
            item = refresh_review_item(
                db,
                item,
                last_record_id=record.id,
                mastery_score=score_after,
                mastery_level=level_after.value,
                status=ReviewItemStatus.PENDING.value,
                interval_days=interval_days,
                next_review_at=next_review_at,
                updated_at=utc_now(),
            )

        db.commit()
        db.refresh(record)
        db.refresh(item)
        return record, item, True
    except IntegrityError:
        db.rollback()
        existing = _existing_result_or_raise(
            db,
            evaluation_id=evaluation.id,
            project_id=project.id,
            knowledge_node_id=node.id,
        )
        if existing is not None:
            return existing
        raise
    except Exception:
        db.rollback()
        raise


def get_mastery_history(
    db: Session,
    *,
    project_id: int,
    knowledge_node_id: int,
    user_id: int,
) -> list[MasteryRecord]:
    project = get_project_by_id_and_user(
        db,
        project_id=project_id,
        user_id=user_id,
    )
    if project is None:
        raise _error(
            "LEARNING_PROJECT_NOT_FOUND",
            "learning project not found",
            status.HTTP_404_NOT_FOUND,
        )
    if (
        get_project_node(
            db,
            project_id=project.id,
            knowledge_node_id=knowledge_node_id,
        )
        is None
    ):
        raise _error(
            "KNOWLEDGE_NODE_NOT_FOUND",
            "knowledge node not found",
            status.HTTP_404_NOT_FOUND,
        )
    return list_records(
        db,
        project_id=project.id,
        knowledge_node_id=knowledge_node_id,
    )


def list_review_items(
    db: Session,
    *,
    project_id: int,
    user_id: int,
) -> list[ReviewItem]:
    project = get_project_by_id_and_user(
        db,
        project_id=project_id,
        user_id=user_id,
    )
    if project is None:
        raise _error(
            "LEARNING_PROJECT_NOT_FOUND",
            "learning project not found",
            status.HTTP_404_NOT_FOUND,
        )
    return repository_list_project_review_items(db, project_id=project.id)


def list_due_review_items(
    db: Session,
    *,
    project_id: int,
    user_id: int,
    now: datetime | None = None,
) -> list[ReviewItem]:
    project = get_project_by_id_and_user(
        db,
        project_id=project_id,
        user_id=user_id,
    )
    if project is None:
        raise _error(
            "LEARNING_PROJECT_NOT_FOUND",
            "learning project not found",
            status.HTTP_404_NOT_FOUND,
        )
    return repository_list_due_review_items(
        db,
        project_id=project.id,
        due_at=now or utc_now(),
    )


def complete_review_item(
    db: Session,
    *,
    review_item_id: int,
    user_id: int,
    completed_at: datetime | None = None,
) -> ReviewItem:
    item = get_owned_review_item(
        db,
        review_item_id=review_item_id,
        user_id=user_id,
    )
    if item is None:
        raise _error(
            "REVIEW_ITEM_NOT_FOUND",
            "review item not found",
            status.HTTP_404_NOT_FOUND,
        )
    if item.status != ReviewItemStatus.PENDING.value:
        raise _error(
            "REVIEW_ITEM_STATE_CONFLICT",
            "only a pending review item can be completed",
            status.HTTP_409_CONFLICT,
        )

    try:
        item = mark_review_completed(
            db,
            item,
            completed_at=completed_at or utc_now(),
        )
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise
