from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evaluation import (
    Evaluation,
    EvaluationDecision,
    RuleEvaluationStatus,
)
from app.models.evidence import Evidence, EvidenceSourceKind, EvidenceType
from app.models.knowledge import KnowledgeNode
from app.models.learning_plan import (
    LearningPlan,
    PlanSourceKind,
    PlanVersion,
    PlanVersionStatus,
)
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskStatus
from app.models.mastery import (
    MasteryLevel,
    MasteryRecord,
    ReviewItem,
    ReviewItemStatus,
)
from app.models.user import User
from app.schemas.mastery import (
    MasteryApplyRequest,
    MasteryApplyResponse,
)
from app.services import mastery_service


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _context(
    db: Session,
    username: str,
    *,
    decision: EvaluationDecision = EvaluationDecision.PASSED,
    finalized: bool = True,
    is_current: bool = True,
) -> tuple[
    User,
    LearningProject,
    KnowledgeNode,
    PlanVersion,
    LearningTask,
    Evaluation,
]:
    user = User(
        username=username,
        password_hash="day138-test-placeholder",
    )
    db.add(user)
    db.flush()

    project = LearningProject(
        user_id=user.id,
        name=f"{username} project",
        goal="verify mastery history",
        current_level="beginner",
    )
    db.add(project)
    db.flush()

    node = KnowledgeNode(
        project_id=project.id,
        title=f"{username} node",
        description="knowledge node for mastery testing",
        difficulty=2,
    )
    plan = LearningPlan(
        project_id=project.id,
        name=f"{username} plan",
    )
    db.add_all([node, plan])
    db.flush()

    version = PlanVersion(
        plan_id=plan.id,
        version_number=1,
        status=PlanVersionStatus.PUBLISHED.value,
        goal="verify mastery",
        content={},
        source_kind=PlanSourceKind.MANUAL.value,
        published_at=utc_now(),
        confirmed_by_user_id=user.id,
        is_current=is_current,
    )
    db.add(version)
    db.flush()

    task_status = (
        TaskStatus(decision.value).value if finalized else TaskStatus.SUBMITTED.value
    )
    task = LearningTask(
        plan_version_id=version.id,
        position=1,
        title="Mastery task",
        objective="Produce evidence",
        instructions="Submit the required evidence",
        steps=["submit"],
        estimated_minutes=20,
        deliverable="answer",
        acceptance_criteria=["answer is reviewed"],
        status=task_status,
        completed_at=utc_now() if task_status == TaskStatus.PASSED.value else None,
    )
    db.add(task)
    db.flush()

    evidence = Evidence(
        plan_version_id=version.id,
        task_id=task.id,
        attempt_number=1,
        evidence_type=EvidenceType.TEXT_ANSWER.value,
        source_kind=EvidenceSourceKind.USER.value,
        text_content="mastery test answer",
        submitted_by_user_id=user.id,
    )
    db.add(evidence)
    db.flush()

    human_decision = decision.value if finalized else None
    confirmed_at = utc_now() if finalized else None
    evaluation = Evaluation(
        evidence_id=evidence.id,
        rule_status=RuleEvaluationStatus.PASS.value,
        rule_result={"checks": [{"name": "answer", "passed": True}]},
        model_suggestion={
            "recommendation": decision.value,
            "reason": "test suggestion",
            "confidence": 0.9,
        },
        human_decision=human_decision,
        human_note="human confirmed" if finalized else None,
        confirmed_by_user_id=user.id if finalized else None,
        confirmed_at=confirmed_at,
        final_decision=human_decision,
        finalized_by_user_id=user.id if finalized else None,
        finalized_at=confirmed_at,
    )
    db.add(evaluation)
    db.commit()

    for value in (user, project, node, version, task, evaluation):
        db.refresh(value)
    return user, project, node, version, task, evaluation


def _additional_final_evaluation(
    db: Session,
    *,
    user: User,
    version: PlanVersion,
    position: int,
    decision: EvaluationDecision,
    finalized_at: datetime,
) -> Evaluation:
    task_status = TaskStatus(decision.value).value
    task = LearningTask(
        plan_version_id=version.id,
        position=position,
        title=f"Mastery task {position}",
        objective="Produce another evidence item",
        instructions="Submit another answer",
        steps=["submit"],
        estimated_minutes=20,
        deliverable="answer",
        acceptance_criteria=["answer is reviewed"],
        status=task_status,
        completed_at=finalized_at if task_status == TaskStatus.PASSED.value else None,
    )
    db.add(task)
    db.flush()

    evidence = Evidence(
        plan_version_id=version.id,
        task_id=task.id,
        attempt_number=1,
        evidence_type=EvidenceType.TEXT_ANSWER.value,
        source_kind=EvidenceSourceKind.USER.value,
        text_content="another mastery answer",
        submitted_by_user_id=user.id,
    )
    db.add(evidence)
    db.flush()

    evaluation = Evaluation(
        evidence_id=evidence.id,
        rule_status=RuleEvaluationStatus.PASS.value,
        rule_result={"checks": [{"name": "answer", "passed": True}]},
        human_decision=decision.value,
        human_note="human confirmed",
        confirmed_by_user_id=user.id,
        confirmed_at=finalized_at,
        final_decision=decision.value,
        finalized_by_user_id=user.id,
        finalized_at=finalized_at,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return evaluation


def _assert_error(
    exc_info: pytest.ExceptionInfo[HTTPException],
    *,
    code: str,
    status_code: int = 409,
) -> None:
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail["code"] == code


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, MasteryLevel.NOVICE),
        (39, MasteryLevel.NOVICE),
        (40, MasteryLevel.DEVELOPING),
        (69, MasteryLevel.DEVELOPING),
        (70, MasteryLevel.PROFICIENT),
        (89, MasteryLevel.PROFICIENT),
        (90, MasteryLevel.MASTERED),
        (100, MasteryLevel.MASTERED),
    ],
)
def test_mastery_level_boundaries(
    score: int,
    expected: MasteryLevel,
) -> None:
    assert mastery_service.mastery_level_for_score(score) == expected


@pytest.mark.parametrize("score", [-1, 101])
def test_mastery_level_rejects_out_of_range(score: int) -> None:
    with pytest.raises(ValueError):
        mastery_service.mastery_level_for_score(score)


def test_mastery_apply_request_requires_positive_node_id() -> None:
    with pytest.raises(ValidationError):
        MasteryApplyRequest(knowledge_node_id=0)


def test_passed_evaluation_creates_history_and_current_review(
    db_session: Session,
) -> None:
    user, project, node, _, _, evaluation = _context(
        db_session,
        "day138-passed",
    )

    record, item, created = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )

    assert created is True
    assert record.project_id == project.id
    assert record.score_before == 0
    assert record.score_after == 20
    assert record.level_after == MasteryLevel.NOVICE.value
    assert record.decision == EvaluationDecision.PASSED.value
    assert record.interval_days == 7
    assert record.algorithm_version == "mastery-v1"
    assert record.calculation["delta"] == 20
    assert item.last_record_id == record.id
    assert item.mastery_score == 20
    assert item.mastery_level == MasteryLevel.NOVICE.value
    assert item.status == ReviewItemStatus.PENDING.value

    response = MasteryApplyResponse.model_validate(
        {"record": record, "review_item": item, "created": created}
    )
    assert response.record.id == record.id
    assert response.review_item.id == item.id


def test_revision_required_uses_short_interval_and_score_floor(
    db_session: Session,
) -> None:
    user, _, node, _, _, evaluation = _context(
        db_session,
        "day138-revision",
        decision=EvaluationDecision.REVISION_REQUIRED,
    )

    record, item, created = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )

    assert created is True
    assert record.score_before == 0
    assert record.score_after == 0
    assert record.interval_days == 1
    assert item.next_review_at == record.next_review_at


def test_second_evaluation_appends_history_and_refreshes_current_review(
    db_session: Session,
) -> None:
    user, project, node, version, _, first_evaluation = _context(
        db_session,
        "day138-history",
    )
    first_record, item, _ = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=first_evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )
    mastery_service.complete_review_item(
        db_session,
        review_item_id=item.id,
        user_id=user.id,
    )

    second_evaluation = _additional_final_evaluation(
        db_session,
        user=user,
        version=version,
        position=2,
        decision=EvaluationDecision.PASSED,
        finalized_at=utc_now() + timedelta(minutes=1),
    )
    second_record, refreshed_item, created = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=second_evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )

    assert created is True
    assert first_record.id != second_record.id
    assert second_record.score_before == 20
    assert second_record.score_after == 40
    assert refreshed_item.id == item.id
    assert refreshed_item.last_record_id == second_record.id
    assert refreshed_item.mastery_score == 40
    assert refreshed_item.status == ReviewItemStatus.PENDING.value
    assert refreshed_item.completed_at is None
    assert refreshed_item.review_count == 1
    assert [
        record.id
        for record in mastery_service.get_mastery_history(
            db_session,
            project_id=project.id,
            knowledge_node_id=node.id,
            user_id=user.id,
        )
    ] == [first_record.id, second_record.id]


def test_duplicate_apply_is_idempotent(
    db_session: Session,
) -> None:
    user, _, node, _, _, evaluation = _context(
        db_session,
        "day138-idempotent",
    )
    first = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )
    second = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )

    assert first[2] is True
    assert second[2] is False
    assert second[0].id == first[0].id
    assert second[1].id == first[1].id
    assert db_session.query(MasteryRecord).count() == 1
    assert db_session.query(ReviewItem).count() == 1


def test_same_evaluation_cannot_be_reassigned_to_another_node(
    db_session: Session,
) -> None:
    user, project, node, _, _, evaluation = _context(
        db_session,
        "day138-node-conflict",
    )
    other_node = KnowledgeNode(
        project_id=project.id,
        title="Other node",
        description="another node",
        difficulty=1,
    )
    db_session.add(other_node)
    db_session.commit()
    db_session.refresh(other_node)

    mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )
    with pytest.raises(HTTPException) as exc_info:
        mastery_service.record_evaluation_mastery(
            db_session,
            evaluation_id=evaluation.id,
            knowledge_node_id=other_node.id,
            user_id=user.id,
        )
    _assert_error(
        exc_info,
        code="MASTERY_EVALUATION_NODE_CONFLICT",
    )


def test_model_suggestion_without_final_decision_cannot_change_mastery(
    db_session: Session,
) -> None:
    user, _, node, _, _, evaluation = _context(
        db_session,
        "day138-not-final",
        finalized=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        mastery_service.record_evaluation_mastery(
            db_session,
            evaluation_id=evaluation.id,
            knowledge_node_id=node.id,
            user_id=user.id,
        )

    _assert_error(
        exc_info,
        code="MASTERY_REQUIRES_FINAL_EVALUATION",
    )
    assert db_session.query(MasteryRecord).count() == 0
    assert db_session.query(ReviewItem).count() == 0


def test_task_status_must_match_final_decision(
    db_session: Session,
) -> None:
    user, _, node, _, task, evaluation = _context(
        db_session,
        "day138-status-mismatch",
    )
    task.status = TaskStatus.REVISION_REQUIRED.value
    task.completed_at = None
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        mastery_service.record_evaluation_mastery(
            db_session,
            evaluation_id=evaluation.id,
            knowledge_node_id=node.id,
            user_id=user.id,
        )

    _assert_error(
        exc_info,
        code="MASTERY_TASK_DECISION_MISMATCH",
    )


def test_cross_project_node_is_hidden(
    db_session: Session,
) -> None:
    user, _, _, _, _, evaluation = _context(
        db_session,
        "day138-owner",
    )
    _, _, outsider_node, _, _, _ = _context(
        db_session,
        "day138-outsider",
    )

    with pytest.raises(HTTPException) as exc_info:
        mastery_service.record_evaluation_mastery(
            db_session,
            evaluation_id=evaluation.id,
            knowledge_node_id=outsider_node.id,
            user_id=user.id,
        )

    _assert_error(
        exc_info,
        code="KNOWLEDGE_NODE_NOT_FOUND",
        status_code=404,
    )


def test_cross_user_evaluation_is_hidden(
    db_session: Session,
) -> None:
    _, _, node, _, _, evaluation = _context(
        db_session,
        "day138-evaluation-owner",
    )
    outsider, _, _, _, _, _ = _context(
        db_session,
        "day138-evaluation-outsider",
    )

    with pytest.raises(HTTPException) as exc_info:
        mastery_service.record_evaluation_mastery(
            db_session,
            evaluation_id=evaluation.id,
            knowledge_node_id=node.id,
            user_id=outsider.id,
        )

    _assert_error(
        exc_info,
        code="EVALUATION_NOT_FOUND",
        status_code=404,
    )


def test_non_current_plan_version_is_rejected(
    db_session: Session,
) -> None:
    user, _, node, _, _, evaluation = _context(
        db_session,
        "day138-old-version",
        is_current=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        mastery_service.record_evaluation_mastery(
            db_session,
            evaluation_id=evaluation.id,
            knowledge_node_id=node.id,
            user_id=user.id,
        )

    _assert_error(exc_info, code="PLAN_VERSION_NOT_ACTIVE")


def test_complete_review_item_and_reject_repeat(
    db_session: Session,
) -> None:
    user, _, node, _, _, evaluation = _context(
        db_session,
        "day138-complete",
    )
    _, item, _ = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )
    completed_at = utc_now()

    item = mastery_service.complete_review_item(
        db_session,
        review_item_id=item.id,
        user_id=user.id,
        completed_at=completed_at,
    )
    assert item.status == ReviewItemStatus.COMPLETED.value
    assert item.review_count == 1
    assert item.last_reviewed_at is not None
    assert item.completed_at is not None
    assert mastery_service._as_utc(item.last_reviewed_at) == completed_at
    assert mastery_service._as_utc(item.completed_at) == completed_at

    with pytest.raises(HTTPException) as exc_info:
        mastery_service.complete_review_item(
            db_session,
            review_item_id=item.id,
            user_id=user.id,
        )
    _assert_error(exc_info, code="REVIEW_ITEM_STATE_CONFLICT")


def test_due_query_only_returns_pending_due_items(
    db_session: Session,
) -> None:
    user, project, node, _, _, evaluation = _context(
        db_session,
        "day138-due",
    )
    _, item, _ = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )

    before_due = mastery_service.list_due_review_items(
        db_session,
        project_id=project.id,
        user_id=user.id,
        now=item.next_review_at - timedelta(seconds=1),
    )
    at_due = mastery_service.list_due_review_items(
        db_session,
        project_id=project.id,
        user_id=user.id,
        now=item.next_review_at,
    )
    assert before_due == []
    assert [value.id for value in at_due] == [item.id]

    mastery_service.complete_review_item(
        db_session,
        review_item_id=item.id,
        user_id=user.id,
    )
    assert (
        mastery_service.list_due_review_items(
            db_session,
            project_id=project.id,
            user_id=user.id,
            now=item.next_review_at + timedelta(days=1),
        )
        == []
    )


def test_history_and_review_queries_enforce_ownership(
    db_session: Session,
) -> None:
    user, project, node, _, _, evaluation = _context(
        db_session,
        "day138-history-owner",
    )
    outsider, _, _, _, _, _ = _context(
        db_session,
        "day138-history-outsider",
    )
    record, item, _ = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )

    assert mastery_service.get_mastery_history(
        db_session,
        project_id=project.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    ) == [record]
    assert mastery_service.list_review_items(
        db_session,
        project_id=project.id,
        user_id=user.id,
    ) == [item]

    with pytest.raises(HTTPException) as history_error:
        mastery_service.get_mastery_history(
            db_session,
            project_id=project.id,
            knowledge_node_id=node.id,
            user_id=outsider.id,
        )
    _assert_error(
        history_error,
        code="LEARNING_PROJECT_NOT_FOUND",
        status_code=404,
    )


def test_derived_write_failure_rolls_back_record_and_review(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, _, node, _, _, evaluation = _context(
        db_session,
        "day138-rollback",
    )

    def fail_create(*_args: object, **_kwargs: object) -> ReviewItem:
        raise RuntimeError("forced review failure")

    monkeypatch.setattr(
        mastery_service,
        "create_review_item",
        fail_create,
    )
    with pytest.raises(RuntimeError, match="forced review failure"):
        mastery_service.record_evaluation_mastery(
            db_session,
            evaluation_id=evaluation.id,
            knowledge_node_id=node.id,
            user_id=user.id,
        )

    assert (
        db_session.scalar(
            select(MasteryRecord).where(MasteryRecord.evaluation_id == evaluation.id)
        )
        is None
    )
    assert db_session.query(ReviewItem).count() == 0


def _invalid_record(
    db: Session,
    *,
    project_id: int,
    node_id: int,
    evaluation_id: int,
    **values: object,
) -> None:
    data: dict[str, object] = {
        "project_id": project_id,
        "knowledge_node_id": node_id,
        "evaluation_id": evaluation_id,
        "score_before": 0,
        "score_after": 20,
        "level_after": MasteryLevel.NOVICE.value,
        "decision": EvaluationDecision.PASSED.value,
        "interval_days": 7,
        "next_review_at": utc_now() + timedelta(days=7),
        "algorithm_version": "mastery-v1",
        "calculation": {"score_after": 20},
        "reason": "valid reason",
        "recorded_at": utc_now(),
    }
    data.update(values)
    db.add(MasteryRecord(**data))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_constraints_reject_invalid_mastery_fields(
    db_session: Session,
) -> None:
    user, project, node, _, _, evaluation = _context(
        db_session,
        "day138-record-constraints",
    )
    del user

    _invalid_record(
        db_session,
        project_id=project.id,
        node_id=node.id,
        evaluation_id=evaluation.id,
        score_after=101,
    )
    _invalid_record(
        db_session,
        project_id=project.id,
        node_id=node.id,
        evaluation_id=evaluation.id,
        level_after="UNKNOWN",
    )
    _invalid_record(
        db_session,
        project_id=project.id,
        node_id=node.id,
        evaluation_id=evaluation.id,
        interval_days=0,
    )
    _invalid_record(
        db_session,
        project_id=project.id,
        node_id=node.id,
        evaluation_id=evaluation.id,
        reason=" ",
    )


def test_database_constraints_reject_invalid_review_fields(
    db_session: Session,
) -> None:
    user, project, node, _, _, evaluation = _context(
        db_session,
        "day138-review-constraints",
    )
    record, _, _ = mastery_service.record_evaluation_mastery(
        db_session,
        evaluation_id=evaluation.id,
        knowledge_node_id=node.id,
        user_id=user.id,
    )
    db_session.execute(
        ReviewItem.__table__.delete().where(ReviewItem.project_id == project.id)
    )
    db_session.commit()

    item = ReviewItem(
        project_id=project.id,
        knowledge_node_id=node.id,
        last_record_id=record.id,
        mastery_score=20,
        mastery_level=MasteryLevel.NOVICE.value,
        status=ReviewItemStatus.COMPLETED.value,
        interval_days=7,
        next_review_at=utc_now() + timedelta(days=7),
        review_count=0,
        last_reviewed_at=None,
        completed_at=None,
    )
    db_session.add(item)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
