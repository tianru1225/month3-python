from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evidence import Evidence, EvidenceSourceKind, EvidenceType
from app.models.evaluation import Evaluation, EvaluationDecision, RuleEvaluationStatus
from app.models.learning_plan import (
    LearningPlan,
    PlanVersion,
    PlanVersionStatus,
)
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskStatus
from app.models.user import User
from app.repositories.evidence_repository import add_evidence
from app.schemas.evaluation import (
    HumanDecisionCreate,
    ModelSuggestionCreate,
    RuleEvaluationCreate,
)
from app.schemas.evidence import EvidenceSourceContext, TextEvidenceCreate
from app.schemas.learning_plan import PlanCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import (
    evidence_service,
    evaluation_service,
    learning_plan_service,
    learning_task_service,
)


def _context(
    db_session: Session,
    username: str,
) -> tuple[User, LearningProject, LearningPlan, PlanVersion, LearningTask]:
    user = User(username=username, password_hash="day137-test-placeholder")
    db_session.add(user)
    db_session.flush()

    project = LearningProject(
        user_id=user.id,
        name=f"{username} project",
        goal="verify evaluation",
        current_level="beginner",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(project)

    plan, version = learning_plan_service.create_plan_with_first_draft(
        db_session,
        project_id=project.id,
        user_id=user.id,
        payload=PlanCreate(
            name=f"{username} plan",
            goal="evaluate submitted evidence",
            content={},
        ),
    )
    task = learning_task_service.create_task(
        db_session,
        plan_version_id=version.id,
        user_id=user.id,
        payload=LearningTaskCreate(
            position=1,
            title="Evaluation task",
            objective="Submit and evaluate evidence",
            instructions="Submit an answer and review it",
            steps=["Submit", "Review"],
            estimated_minutes=30,
            deliverable="An evaluated answer",
            acceptance_criteria=["Evaluation is finalized by a human"],
        ),
    )
    return user, project, plan, version, task


def _activate(
    db_session: Session,
    *,
    user: User,
    plan: LearningPlan,
    version: PlanVersion,
    task: LearningTask,
) -> LearningTask:
    learning_plan_service.publish_version(
        db_session,
        plan_id=plan.id,
        version_id=version.id,
        user_id=user.id,
    )
    for target in (TaskStatus.READY, TaskStatus.IN_PROGRESS):
        task = learning_task_service.transition_task_status(
            db_session,
            plan_version_id=version.id,
            task_id=task.id,
            user_id=user.id,
            target_status=target,
        )
    return task


def _submitted_context(
    db_session: Session,
    username: str,
) -> tuple[User, LearningProject, LearningPlan, PlanVersion, LearningTask, Evidence]:
    user, project, plan, version, task = _context(db_session, username)
    task = _activate(
        db_session,
        user=user,
        plan=plan,
        version=version,
        task=task,
    )
    evidence = evidence_service.submit_evidence(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        payload=TextEvidenceCreate(text_content="answer for evaluation"),
        source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
    )
    db_session.refresh(task)
    db_session.refresh(evidence)
    return user, project, plan, version, task, evidence


def _rule_payload(evidence_id: int) -> RuleEvaluationCreate:
    return RuleEvaluationCreate(
        evidence_id=evidence_id,
        rule_status=RuleEvaluationStatus.PASS,
        rule_result={
            "checks": [
                {
                    "name": "answer_present",
                    "passed": True,
                }
            ]
        },
    )


def _suggestion_payload(
    recommendation: EvaluationDecision = EvaluationDecision.PASSED,
) -> ModelSuggestionCreate:
    return ModelSuggestionCreate(
        recommendation=recommendation,
        reason="structured model suggestion only",
        confidence=0.92,
        model_name="day137-test-model",
    )


def _human_payload(
    decision: EvaluationDecision = EvaluationDecision.PASSED,
) -> HumanDecisionCreate:
    return HumanDecisionCreate(
        decision=decision,
        note="human decision for the submitted evidence",
    )


def _assert_error(
    error: pytest.ExceptionInfo[HTTPException],
    *,
    code: str,
    status_code: int = 409,
) -> None:
    assert error.value.status_code == status_code
    assert error.value.detail["code"] == code


def test_create_evaluation_starts_without_model_or_human_decision(
    db_session: Session,
) -> None:
    user, _, _, version, task, evidence = _submitted_context(
        db_session,
        "day137-create",
    )

    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )

    assert evaluation.evidence_id == evidence.id
    assert evaluation.rule_status == RuleEvaluationStatus.PASS.value
    assert evaluation.rule_result["checks"][0]["passed"] is True
    assert evaluation.model_suggestion is None
    assert evaluation.human_decision is None
    assert evaluation.final_decision is None
    assert task.status == TaskStatus.SUBMITTED.value
    assert version.status == PlanVersionStatus.PUBLISHED.value


def test_duplicate_evaluation_is_rejected(db_session: Session) -> None:
    user, _, _, _, _, evidence = _submitted_context(
        db_session,
        "day137-duplicate",
    )
    evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )

    with pytest.raises(HTTPException) as error:
        evaluation_service.create_evaluation(
            db_session,
            evidence_id=evidence.id,
            user_id=user.id,
            payload=_rule_payload(evidence.id),
        )

    _assert_error(error, code="EVALUATION_ALREADY_EXISTS")


def test_payload_evidence_id_must_match_argument(db_session: Session) -> None:
    user, _, _, _, _, evidence = _submitted_context(
        db_session,
        "day137-id-mismatch",
    )

    with pytest.raises(HTTPException) as error:
        evaluation_service.create_evaluation(
            db_session,
            evidence_id=evidence.id,
            user_id=user.id,
            payload=RuleEvaluationCreate(
                evidence_id=evidence.id + 1,
                rule_status=RuleEvaluationStatus.PASS,
                rule_result={"checks": [{"passed": True}]},
            ),
        )

    _assert_error(
        error,
        code="EVIDENCE_ID_MISMATCH",
        status_code=400,
    )


def test_model_suggestion_is_isolated_from_task_and_final_decision(
    db_session: Session,
) -> None:
    user, _, _, _, task, evidence = _submitted_context(
        db_session,
        "day137-model",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )

    evaluation = evaluation_service.record_model_suggestion(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=_suggestion_payload(EvaluationDecision.REVISION_REQUIRED),
    )

    db_session.refresh(task)
    assert evaluation.model_suggestion is not None
    assert evaluation.model_suggestion["recommendation"] == "REVISION_REQUIRED"
    assert evaluation.final_decision is None
    assert task.status == TaskStatus.SUBMITTED.value


def test_human_confirmation_does_not_finalize_task(
    db_session: Session,
) -> None:
    user, _, _, _, task, evidence = _submitted_context(
        db_session,
        "day137-human",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )

    evaluation = evaluation_service.confirm_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=_human_payload(),
    )

    db_session.refresh(task)
    assert evaluation.human_decision == EvaluationDecision.PASSED.value
    assert evaluation.human_note == "human decision for the submitted evidence"
    assert evaluation.confirmed_by_user_id == user.id
    assert evaluation.confirmed_at is not None
    assert evaluation.final_decision is None
    assert task.status == TaskStatus.SUBMITTED.value


def test_finalize_requires_human_confirmation(db_session: Session) -> None:
    user, _, _, _, task, evidence = _submitted_context(
        db_session,
        "day137-human-required",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )

    with pytest.raises(HTTPException) as error:
        evaluation_service.finalize_evaluation(
            db_session,
            evaluation_id=evaluation.id,
            user_id=user.id,
        )

    _assert_error(error, code="HUMAN_DECISION_REQUIRED")
    db_session.refresh(task)
    db_session.refresh(evaluation)
    assert evaluation.final_decision is None
    assert task.status == TaskStatus.SUBMITTED.value


def test_human_passed_finalizes_task_as_passed(db_session: Session) -> None:
    user, _, _, _, task, evidence = _submitted_context(
        db_session,
        "day137-passed",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )
    evaluation_service.confirm_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=_human_payload(EvaluationDecision.PASSED),
    )

    evaluation = evaluation_service.finalize_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
    )

    db_session.refresh(task)
    assert evaluation.final_decision == EvaluationDecision.PASSED.value
    assert evaluation.finalized_by_user_id == user.id
    assert evaluation.finalized_at is not None
    assert task.status == TaskStatus.PASSED.value
    assert task.completed_at is not None


def test_human_revision_finalizes_task_as_revision_required(
    db_session: Session,
) -> None:
    user, _, _, _, task, evidence = _submitted_context(
        db_session,
        "day137-revision",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )
    evaluation_service.confirm_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=_human_payload(EvaluationDecision.REVISION_REQUIRED),
    )

    evaluation = evaluation_service.finalize_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
    )

    db_session.refresh(task)
    assert evaluation.final_decision == EvaluationDecision.REVISION_REQUIRED.value
    assert evaluation.finalized_by_user_id == user.id
    assert evaluation.finalized_at is not None
    assert task.status == TaskStatus.REVISION_REQUIRED.value
    assert task.completed_at is None


def test_human_decision_wins_over_conflicting_model_suggestion(
    db_session: Session,
) -> None:
    user, _, _, _, task, evidence = _submitted_context(
        db_session,
        "day137-conflict",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )
    evaluation_service.record_model_suggestion(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=_suggestion_payload(EvaluationDecision.REVISION_REQUIRED),
    )
    evaluation_service.confirm_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=_human_payload(EvaluationDecision.PASSED),
    )

    evaluation = evaluation_service.finalize_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
    )

    db_session.refresh(task)
    assert evaluation.model_suggestion["recommendation"] == "REVISION_REQUIRED"
    assert evaluation.human_decision == EvaluationDecision.PASSED.value
    assert evaluation.final_decision == EvaluationDecision.PASSED.value
    assert task.status == TaskStatus.PASSED.value


def test_finalized_evaluation_is_immutable_for_later_actions(
    db_session: Session,
) -> None:
    user, _, _, _, task, evidence = _submitted_context(
        db_session,
        "day137-finalized",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )
    evaluation_service.confirm_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=_human_payload(),
    )
    evaluation_service.finalize_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
    )

    with pytest.raises(HTTPException) as suggestion_error:
        evaluation_service.record_model_suggestion(
            db_session,
            evaluation_id=evaluation.id,
            user_id=user.id,
            payload=_suggestion_payload(EvaluationDecision.REVISION_REQUIRED),
        )
    _assert_error(suggestion_error, code="MODEL_SUGGESTION_FINALIZED")

    with pytest.raises(HTTPException) as finalize_error:
        evaluation_service.finalize_evaluation(
            db_session,
            evaluation_id=evaluation.id,
            user_id=user.id,
        )
    _assert_error(finalize_error, code="EVALUATION_ALREADY_FINALIZED")
    db_session.refresh(task)
    assert task.status == TaskStatus.PASSED.value


def test_old_attempt_cannot_be_evaluated(db_session: Session) -> None:
    user, _, plan, version, task, first = _submitted_context(
        db_session,
        "day137-old-attempt",
    )
    learning_task_service.transition_task_status(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        target_status=TaskStatus.REVISION_REQUIRED,
    )
    task = learning_task_service.transition_task_status(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        target_status=TaskStatus.IN_PROGRESS,
    )
    second = evidence_service.submit_evidence(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        payload=TextEvidenceCreate(text_content="second answer"),
        source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
    )

    with pytest.raises(HTTPException) as error:
        evaluation_service.create_evaluation(
            db_session,
            evidence_id=first.id,
            user_id=user.id,
            payload=_rule_payload(first.id),
        )

    _assert_error(error, code="EVIDENCE_NOT_LATEST")
    assert second.attempt_number == 2


def test_non_submitted_task_cannot_be_evaluated(db_session: Session) -> None:
    user, _, plan, version, task = _context(db_session, "day137-not-submitted")
    learning_plan_service.publish_version(
        db_session,
        plan_id=plan.id,
        version_id=version.id,
        user_id=user.id,
    )
    task = learning_task_service.transition_task_status(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        target_status=TaskStatus.READY,
    )
    evidence = add_evidence(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        attempt_number=1,
        evidence_type=EvidenceType.TEXT_ANSWER.value,
        source_kind=EvidenceSourceKind.USER.value,
        source_ref=None,
        text_content="direct test fixture evidence",
        test_report=None,
        submitted_by_user_id=user.id,
    )
    db_session.commit()
    db_session.refresh(evidence)

    with pytest.raises(HTTPException) as error:
        evaluation_service.create_evaluation(
            db_session,
            evidence_id=evidence.id,
            user_id=user.id,
            payload=_rule_payload(evidence.id),
        )

    _assert_error(error, code="EVIDENCE_NOT_SUBMITTED")


def test_non_current_version_cannot_be_evaluated(db_session: Session) -> None:
    user, _, plan, old_version, task, evidence = _submitted_context(
        db_session,
        "day137-old-version",
    )
    new_version = learning_plan_service.create_next_draft(
        db_session,
        plan_id=plan.id,
        user_id=user.id,
        payload=PlanCreate(
            name="unused",
            goal="new version",
            content={},
        ),
    )
    assert new_version.status == PlanVersionStatus.DRAFT.value
    learning_plan_service.publish_version(
        db_session,
        plan_id=plan.id,
        version_id=new_version.id,
        user_id=user.id,
    )

    with pytest.raises(HTTPException) as error:
        evaluation_service.create_evaluation(
            db_session,
            evidence_id=evidence.id,
            user_id=user.id,
            payload=_rule_payload(evidence.id),
        )

    _assert_error(error, code="PLAN_VERSION_NOT_ACTIVE")
    assert old_version.is_current is False


def test_unauthorized_user_cannot_read_or_write_evaluation(
    db_session: Session,
) -> None:
    user, _, _, _, _, evidence = _submitted_context(
        db_session,
        "day137-owner",
    )
    outsider = User(
        username="day137-outsider",
        password_hash="day137-outsider-placeholder",
    )
    db_session.add(outsider)
    db_session.commit()
    db_session.refresh(outsider)

    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )

    with pytest.raises(HTTPException) as create_error:
        evaluation_service.create_evaluation(
            db_session,
            evidence_id=evidence.id,
            user_id=outsider.id,
            payload=_rule_payload(evidence.id),
        )
    _assert_error(create_error, code="EVIDENCE_NOT_FOUND", status_code=404)

    with pytest.raises(HTTPException) as read_error:
        evaluation_service.get_evaluation(
            db_session,
            evaluation_id=evaluation.id,
            user_id=outsider.id,
        )
    _assert_error(read_error, code="EVALUATION_NOT_FOUND", status_code=404)

    with pytest.raises(HTTPException) as suggestion_error:
        evaluation_service.record_model_suggestion(
            db_session,
            evaluation_id=evaluation.id,
            user_id=outsider.id,
            payload=_suggestion_payload(),
        )
    _assert_error(suggestion_error, code="EVALUATION_NOT_FOUND", status_code=404)

    with pytest.raises(HTTPException) as confirm_error:
        evaluation_service.confirm_evaluation(
            db_session,
            evaluation_id=evaluation.id,
            user_id=outsider.id,
            payload=_human_payload(),
        )
    _assert_error(confirm_error, code="EVALUATION_NOT_FOUND", status_code=404)

    with pytest.raises(HTTPException) as finalize_error:
        evaluation_service.finalize_evaluation(
            db_session,
            evaluation_id=evaluation.id,
            user_id=outsider.id,
        )
    _assert_error(finalize_error, code="EVALUATION_NOT_FOUND", status_code=404)


def test_finalize_rolls_back_evaluation_and_task_on_transition_failure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, _, _, _, task, evidence = _submitted_context(
        db_session,
        "day137-rollback",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )
    evaluation_service.confirm_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=_human_payload(),
    )

    def fail_transition(*_: object, **__: object) -> LearningTask:
        raise HTTPException(
            status_code=409,
            detail={"code": "TASK_STATUS_CONFLICT", "message": "forced conflict"},
        )

    monkeypatch.setattr(
        evaluation_service,
        "transition_task_status",
        fail_transition,
    )

    with pytest.raises(HTTPException) as error:
        evaluation_service.finalize_evaluation(
            db_session,
            evaluation_id=evaluation.id,
            user_id=user.id,
        )

    _assert_error(error, code="EVALUATION_FINALIZE_CONFLICT")
    db_session.refresh(evaluation)
    db_session.refresh(task)
    assert evaluation.final_decision is None
    assert task.status == TaskStatus.SUBMITTED.value


def _commit_invalid_evaluation(
    db_session: Session,
    *,
    evidence_id: int,
    **values: object,
) -> None:
    payload: dict[str, object] = {
        "evidence_id": evidence_id,
        "rule_status": RuleEvaluationStatus.PASS.value,
        "rule_result": {"checks": [{"passed": True}]},
    }
    payload.update(values)
    row = Evaluation(**payload)
    db_session.add(row)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_constraints_reject_invalid_evaluation_fields(
    db_session: Session,
) -> None:
    user, _, _, _, _, evidence = _submitted_context(
        db_session,
        "day137-constraints",
    )

    _commit_invalid_evaluation(
        db_session,
        evidence_id=evidence.id,
        rule_status="UNKNOWN",
    )
    _commit_invalid_evaluation(
        db_session,
        evidence_id=evidence.id,
        human_decision="UNKNOWN",
        human_note="invalid decision",
        confirmed_by_user_id=user.id,
        confirmed_at=datetime.now(timezone.utc),
    )
    _commit_invalid_evaluation(
        db_session,
        evidence_id=evidence.id,
        final_decision=EvaluationDecision.PASSED.value,
        finalized_by_user_id=user.id,
        finalized_at=datetime.now(timezone.utc),
    )


def test_database_rejects_final_decision_mismatch_with_human(
    db_session: Session,
) -> None:
    user, _, _, _, _, evidence = _submitted_context(
        db_session,
        "day137-mismatch",
    )
    _commit_invalid_evaluation(
        db_session,
        evidence_id=evidence.id,
        human_decision=EvaluationDecision.PASSED.value,
        human_note="human passed",
        confirmed_by_user_id=user.id,
        confirmed_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        final_decision=EvaluationDecision.REVISION_REQUIRED.value,
        finalized_by_user_id=user.id,
        finalized_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )


def test_optional_json_none_is_stored_as_sql_null(db_session: Session) -> None:
    user, _, _, _, _, evidence = _submitted_context(
        db_session,
        "day137-json-null",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )

    evaluation.model_suggestion = None
    db_session.commit()
    stored = db_session.execute(
        text("SELECT model_suggestion FROM evaluations WHERE id = :id"),
        {"id": evaluation.id},
    ).scalar_one()
    assert stored is None


def test_commands_in_suggestion_are_stored_but_never_executed(
    db_session: Session,
) -> None:
    user, _, _, _, task, evidence = _submitted_context(
        db_session,
        "day137-command",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )
    payload = ModelSuggestionCreate(
        recommendation=EvaluationDecision.PASSED,
        reason="run pytest -q only as text",
        confidence=0.5,
        model_name="command-test",
    )
    evaluation_service.record_model_suggestion(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=payload,
    )

    db_session.refresh(task)
    assert task.status == TaskStatus.SUBMITTED.value
    assert evaluation.model_suggestion["reason"] == "run pytest -q only as text"


def test_get_evaluation_allows_owner_to_read_finalized_result(
    db_session: Session,
) -> None:
    user, _, _, _, _, evidence = _submitted_context(
        db_session,
        "day137-read-finalized",
    )
    evaluation = evaluation_service.create_evaluation(
        db_session,
        evidence_id=evidence.id,
        user_id=user.id,
        payload=_rule_payload(evidence.id),
    )
    evaluation_service.confirm_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
        payload=_human_payload(),
    )
    evaluation_service.finalize_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
    )

    loaded = evaluation_service.get_evaluation(
        db_session,
        evaluation_id=evaluation.id,
        user_id=user.id,
    )
    assert loaded.final_decision == EvaluationDecision.PASSED.value
