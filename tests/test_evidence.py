import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evidence import Evidence, EvidenceSourceKind, EvidenceType
from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskStatus
from app.models.user import User
from app.schemas.evidence import (
    EvidenceCreate,
    EvidenceSourceContext,
    StructuredTestReport,
    TestCheck as EvidenceTestCheck,
    TestCheckStatus as EvidenceTestCheckStatus,
    TestReportEvidenceCreate as EvidenceTestReportCreate,
    TextEvidenceCreate,
)
from app.schemas.learning_plan import PlanCreate, PlanVersionCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import (
    evidence_service,
    learning_plan_service,
    learning_task_service,
)


def _context(
    db_session: Session,
    username: str,
) -> tuple[User, LearningProject, LearningPlan, PlanVersion, LearningTask]:
    user = User(username=username, password_hash="day136-test-placeholder")
    db_session.add(user)
    db_session.flush()
    project = LearningProject(
        user_id=user.id,
        name=f"{username} project",
        goal="verify evidence",
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
            goal="submit evidence",
            content={},
        ),
    )
    task = learning_task_service.create_task(
        db_session,
        plan_version_id=version.id,
        user_id=user.id,
        payload=LearningTaskCreate(
            position=1,
            title="Evidence task",
            objective="Submit a result",
            instructions="Complete and submit",
            steps=["Complete", "Verify"],
            estimated_minutes=30,
            deliverable="A result",
            acceptance_criteria=["Evidence is structured"],
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


def _report() -> StructuredTestReport:
    return StructuredTestReport(
        command="pytest -q",
        exit_code=0,
        summary="All selected tests passed",
        checks=[
            EvidenceTestCheck(
                name="unit tests",
                status=EvidenceTestCheckStatus.PASSED,
            ),
            EvidenceTestCheck(
                name="lint",
                status=EvidenceTestCheckStatus.SKIPPED,
                details="not part of this run",
            ),
        ],
        duration_ms=1200,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"evidence_type": "TEXT_ANSWER", "text_content": " "},
        {"evidence_type": "TEST_REPORT", "test_report": {"command": "x"}},
        {"evidence_type": "UNKNOWN", "text_content": "answer"},
    ],
)
def test_evidence_payload_schema_rejects_invalid_data(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(EvidenceCreate).validate_python(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "USER", "reference": "should-not-exist"},
        {"kind": "AUTOMATION"},
        {"kind": "AUTOMATION", "reference": " "},
    ],
)
def test_source_context_rejects_inconsistent_reference(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        EvidenceSourceContext.model_validate(payload)


def test_submit_text_evidence_appends_and_submits_task(db_session: Session) -> None:
    user, _, plan, version, task = _context(db_session, "day136-text")
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
        payload=TextEvidenceCreate(text_content="  My answer  "),
        source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
    )

    db_session.refresh(task)
    assert evidence.evidence_type == EvidenceType.TEXT_ANSWER.value
    assert evidence.text_content == "My answer"
    assert evidence.test_report is None
    assert evidence.attempt_number == 1
    assert evidence.submitted_by_user_id == user.id
    assert task.status == TaskStatus.SUBMITTED.value


def test_submit_structured_report_preserves_automation_source(
    db_session: Session,
) -> None:
    user, _, plan, version, task = _context(db_session, "day136-report")
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
        payload=EvidenceTestReportCreate(test_report=_report()),
        source=EvidenceSourceContext(
            kind=EvidenceSourceKind.AUTOMATION,
            reference="rq-job:day136-test",
        ),
    )

    assert evidence.evidence_type == EvidenceType.TEST_REPORT.value
    assert evidence.text_content is None
    assert evidence.test_report is not None
    assert evidence.test_report["command"] == "pytest -q"
    assert evidence.test_report["checks"][0]["status"] == "PASSED"
    assert evidence.source_kind == EvidenceSourceKind.AUTOMATION.value
    assert evidence.source_ref == "rq-job:day136-test"


def test_revision_submission_appends_second_attempt(db_session: Session) -> None:
    user, _, plan, version, task = _context(db_session, "day136-attempt")
    task = _activate(
        db_session,
        user=user,
        plan=plan,
        version=version,
        task=task,
    )
    first = evidence_service.submit_evidence(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        payload=TextEvidenceCreate(text_content="first answer"),
        source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
    )
    for target in (TaskStatus.REVISION_REQUIRED, TaskStatus.IN_PROGRESS):
        task = learning_task_service.transition_task_status(
            db_session,
            plan_version_id=version.id,
            task_id=task.id,
            user_id=user.id,
            target_status=target,
        )
    second = evidence_service.submit_evidence(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        payload=TextEvidenceCreate(text_content="revised answer"),
        source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
    )

    history = evidence_service.list_task_evidence(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
    )
    assert [item.id for item in history] == [first.id, second.id]
    assert [item.attempt_number for item in history] == [1, 2]
    assert [item.text_content for item in history] == [
        "first answer",
        "revised answer",
    ]


def test_wrong_status_and_inactive_version_reject_submission(
    db_session: Session,
) -> None:
    user, _, plan, version, task = _context(db_session, "day136-status")
    with pytest.raises(HTTPException) as draft_error:
        evidence_service.submit_evidence(
            db_session,
            plan_version_id=version.id,
            task_id=task.id,
            user_id=user.id,
            payload=TextEvidenceCreate(text_content="too early"),
            source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
        )
    assert draft_error.value.detail["code"] == "PLAN_VERSION_NOT_ACTIVE"

    learning_plan_service.publish_version(
        db_session,
        plan_id=plan.id,
        version_id=version.id,
        user_id=user.id,
    )
    with pytest.raises(HTTPException) as ready_error:
        evidence_service.submit_evidence(
            db_session,
            plan_version_id=version.id,
            task_id=task.id,
            user_id=user.id,
            payload=TextEvidenceCreate(text_content="still too early"),
            source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
        )
    assert ready_error.value.detail["code"] == "TASK_NOT_ACCEPTING_EVIDENCE"

    task = learning_task_service.transition_task_status(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        target_status=TaskStatus.READY,
    )
    task = learning_task_service.transition_task_status(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        target_status=TaskStatus.IN_PROGRESS,
    )
    replacement = learning_plan_service.create_next_draft(
        db_session,
        plan_id=plan.id,
        user_id=user.id,
        payload=PlanVersionCreate(goal="replacement", content={}),
    )
    learning_plan_service.publish_version(
        db_session,
        plan_id=plan.id,
        version_id=replacement.id,
        user_id=user.id,
    )
    with pytest.raises(HTTPException) as inactive_error:
        evidence_service.submit_evidence(
            db_session,
            plan_version_id=version.id,
            task_id=task.id,
            user_id=user.id,
            payload=TextEvidenceCreate(text_content="old version"),
            source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
        )
    assert inactive_error.value.detail["code"] == "PLAN_VERSION_NOT_ACTIVE"


def test_owner_and_task_scope_are_hidden(db_session: Session) -> None:
    owner, _, plan, version, task = _context(db_session, "day136-owner")
    other, _, _, _, _ = _context(db_session, "day136-other")
    task = _activate(
        db_session,
        user=owner,
        plan=plan,
        version=version,
        task=task,
    )

    with pytest.raises(HTTPException) as owner_error:
        evidence_service.submit_evidence(
            db_session,
            plan_version_id=version.id,
            task_id=task.id,
            user_id=other.id,
            payload=TextEvidenceCreate(text_content="forbidden"),
            source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
        )
    assert owner_error.value.status_code == 404
    assert owner_error.value.detail["code"] == "PLAN_VERSION_NOT_FOUND"

    with pytest.raises(HTTPException) as task_error:
        evidence_service.list_task_evidence(
            db_session,
            plan_version_id=version.id,
            task_id=task.id + 100_000,
            user_id=owner.id,
        )
    assert task_error.value.status_code == 404
    assert task_error.value.detail["code"] == "LEARNING_TASK_NOT_FOUND"


def test_transition_failure_rolls_back_evidence(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, _, plan, version, task = _context(db_session, "day136-rollback")
    task = _activate(
        db_session,
        user=user,
        plan=plan,
        version=version,
        task=task,
    )

    def fail_transition(*_: object, **__: object) -> LearningTask:
        raise HTTPException(
            status_code=409,
            detail={"code": "TASK_STATUS_CONFLICT", "message": "conflict"},
        )

    monkeypatch.setattr(evidence_service, "transition_task_status", fail_transition)
    with pytest.raises(HTTPException):
        evidence_service.submit_evidence(
            db_session,
            plan_version_id=version.id,
            task_id=task.id,
            user_id=user.id,
            payload=TextEvidenceCreate(text_content="must roll back"),
            source=EvidenceSourceContext(kind=EvidenceSourceKind.USER),
        )

    assert (
        evidence_service.list_task_evidence(
            db_session,
            plan_version_id=version.id,
            task_id=task.id,
            user_id=user.id,
        )
        == []
    )
    db_session.refresh(task)
    assert task.status == TaskStatus.IN_PROGRESS.value


def test_database_constraints_reject_invalid_payload_source_and_attempt(
    db_session: Session,
) -> None:
    user, _, _, version, task = _context(db_session, "day136-db")
    invalid_rows = [
        Evidence(
            plan_version_id=version.id,
            task_id=task.id,
            attempt_number=0,
            evidence_type=EvidenceType.TEXT_ANSWER.value,
            source_kind=EvidenceSourceKind.USER.value,
            text_content="answer",
            submitted_by_user_id=user.id,
        ),
        Evidence(
            plan_version_id=version.id,
            task_id=task.id,
            attempt_number=1,
            evidence_type=EvidenceType.TEXT_ANSWER.value,
            source_kind=EvidenceSourceKind.USER.value,
            text_content="answer",
            test_report={"unexpected": True},
            submitted_by_user_id=user.id,
        ),
        Evidence(
            plan_version_id=version.id,
            task_id=task.id,
            attempt_number=1,
            evidence_type=EvidenceType.TEST_REPORT.value,
            source_kind=EvidenceSourceKind.AUTOMATION.value,
            test_report={"command": "pytest"},
            source_ref=None,
            submitted_by_user_id=user.id,
        ),
    ]
    for row in invalid_rows:
        db_session.add(row)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


def test_composite_foreign_key_encodes_same_version_rule() -> None:
    constraints = [
        constraint
        for constraint in Evidence.__table__.foreign_key_constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]
    pairs = {
        (
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in constraints
    }
    assert (
        ("task_id", "plan_version_id"),
        ("learning_tasks.id", "learning_tasks.plan_version_id"),
    ) in pairs


def test_database_rejects_duplicate_attempt(
    db_session: Session,
) -> None:
    user, _, _, version, task = _context(db_session, "day136-duplicate")
    first = Evidence(
        plan_version_id=version.id,
        task_id=task.id,
        attempt_number=1,
        evidence_type=EvidenceType.TEXT_ANSWER.value,
        source_kind=EvidenceSourceKind.USER.value,
        text_content="first attempt",
        submitted_by_user_id=user.id,
    )
    db_session.add(first)
    db_session.commit()

    duplicate = Evidence(
        plan_version_id=version.id,
        task_id=task.id,
        attempt_number=1,
        evidence_type=EvidenceType.TEXT_ANSWER.value,
        source_kind=EvidenceSourceKind.USER.value,
        text_content="duplicate attempt",
        submitted_by_user_id=user.id,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
