import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.task_state import (
    InvalidTaskStatusTransition,
    allowed_task_status_targets,
    require_task_status_transition,
)
from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskStatus
from app.models.user import User
from app.repositories.learning_task_repository import compare_and_set_task_status
from app.schemas.learning_plan import PlanCreate, PlanVersionCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import learning_plan_service, learning_task_service


ALLOWED_TRANSITIONS = {
    (TaskStatus.DRAFT, TaskStatus.READY),
    (TaskStatus.READY, TaskStatus.IN_PROGRESS),
    (TaskStatus.IN_PROGRESS, TaskStatus.SUBMITTED),
    (TaskStatus.SUBMITTED, TaskStatus.PASSED),
    (TaskStatus.SUBMITTED, TaskStatus.REVISION_REQUIRED),
    (TaskStatus.REVISION_REQUIRED, TaskStatus.IN_PROGRESS),
}

INVALID_TRANSITIONS = [
    (current, target)
    for current in TaskStatus
    for target in TaskStatus
    if current != target and (current, target) not in ALLOWED_TRANSITIONS
]


def _context(
    db_session: Session,
    username: str,
) -> tuple[User, LearningProject, LearningPlan, PlanVersion]:
    user = User(username=username, password_hash="day135-test-placeholder")
    db_session.add(user)
    db_session.flush()
    project = LearningProject(
        user_id=user.id,
        name=f"{username} project",
        goal="verify task status transitions",
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
            goal="complete the state machine",
            content={},
        ),
    )
    return user, project, plan, version


def _payload(position: int) -> LearningTaskCreate:
    return LearningTaskCreate(
        position=position,
        title=f"Task {position}",
        objective=f"Objective {position}",
        instructions=f"Instructions {position}",
        steps=[f"Step {position}"],
        estimated_minutes=30,
        deliverable=f"Deliverable {position}",
        acceptance_criteria=[f"Criterion {position}"],
    )


def _task(
    db_session: Session,
    *,
    version_id: int,
    user_id: int,
    position: int,
) -> LearningTask:
    return learning_task_service.create_task(
        db_session,
        plan_version_id=version_id,
        user_id=user_id,
        payload=_payload(position),
    )


def _publish(
    db_session: Session,
    *,
    plan_id: int,
    version_id: int,
    user_id: int,
) -> PlanVersion:
    return learning_plan_service.publish_version(
        db_session,
        plan_id=plan_id,
        version_id=version_id,
        user_id=user_id,
    )


def _transition(
    db_session: Session,
    *,
    task: LearningTask,
    user_id: int,
    target: TaskStatus,
) -> LearningTask:
    return learning_task_service.transition_task_status(
        db_session,
        plan_version_id=task.plan_version_id,
        task_id=task.id,
        user_id=user_id,
        target_status=target,
    )


@pytest.mark.parametrize(
    ("current", "target"),
    sorted(
        ALLOWED_TRANSITIONS,
        key=lambda pair: (pair[0].value, pair[1].value),
    ),
)
def test_state_machine_accepts_only_declared_edges(
    current: TaskStatus,
    target: TaskStatus,
) -> None:
    require_task_status_transition(current, target)
    assert target in allowed_task_status_targets(current)


@pytest.mark.parametrize(("current", "target"), INVALID_TRANSITIONS)
def test_state_machine_rejects_every_undeclared_edge(
    current: TaskStatus,
    target: TaskStatus,
) -> None:
    with pytest.raises(InvalidTaskStatusTransition) as error:
        require_task_status_transition(current, target)
    assert error.value.current == current
    assert error.value.target == target


def test_happy_path_sets_completion_only_when_passed(db_session: Session) -> None:
    user, _, plan, version = _context(db_session, "day135-happy")
    task = _task(
        db_session,
        version_id=version.id,
        user_id=user.id,
        position=1,
    )
    _publish(
        db_session,
        plan_id=plan.id,
        version_id=version.id,
        user_id=user.id,
    )

    for target in (
        TaskStatus.READY,
        TaskStatus.IN_PROGRESS,
        TaskStatus.SUBMITTED,
    ):
        task = _transition(
            db_session,
            task=task,
            user_id=user.id,
            target=target,
        )
        assert task.status == target.value
        assert task.completed_at is None

    task = _transition(
        db_session,
        task=task,
        user_id=user.id,
        target=TaskStatus.PASSED,
    )
    assert task.status == TaskStatus.PASSED.value
    assert task.completed_at is not None


def test_revision_path_and_same_status_are_idempotent(db_session: Session) -> None:
    user, _, plan, version = _context(db_session, "day135-revision")
    task = _task(
        db_session,
        version_id=version.id,
        user_id=user.id,
        position=1,
    )
    _publish(
        db_session,
        plan_id=plan.id,
        version_id=version.id,
        user_id=user.id,
    )

    for target in (
        TaskStatus.READY,
        TaskStatus.IN_PROGRESS,
        TaskStatus.SUBMITTED,
        TaskStatus.REVISION_REQUIRED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.SUBMITTED,
        TaskStatus.PASSED,
    ):
        task = _transition(
            db_session,
            task=task,
            user_id=user.id,
            target=target,
        )

    first_completed_at = task.completed_at
    same = _transition(
        db_session,
        task=task,
        user_id=user.id,
        target=TaskStatus.PASSED,
    )
    assert same.id == task.id
    assert same.completed_at == first_completed_at


def test_draft_and_inactive_published_versions_cannot_run(db_session: Session) -> None:
    user, _, plan, first_version = _context(db_session, "day135-active")
    old_task = _task(
        db_session,
        version_id=first_version.id,
        user_id=user.id,
        position=1,
    )

    with pytest.raises(HTTPException) as draft_error:
        _transition(
            db_session,
            task=old_task,
            user_id=user.id,
            target=TaskStatus.READY,
        )
    assert draft_error.value.status_code == 409
    assert draft_error.value.detail["code"] == "PLAN_VERSION_NOT_ACTIVE"

    _publish(
        db_session,
        plan_id=plan.id,
        version_id=first_version.id,
        user_id=user.id,
    )
    second_version = learning_plan_service.create_next_draft(
        db_session,
        plan_id=plan.id,
        user_id=user.id,
        payload=PlanVersionCreate(goal="replacement", content={}),
    )
    _task(
        db_session,
        version_id=second_version.id,
        user_id=user.id,
        position=1,
    )
    _publish(
        db_session,
        plan_id=plan.id,
        version_id=second_version.id,
        user_id=user.id,
    )

    with pytest.raises(HTTPException) as inactive_error:
        _transition(
            db_session,
            task=old_task,
            user_id=user.id,
            target=TaskStatus.READY,
        )
    assert inactive_error.value.status_code == 409
    assert inactive_error.value.detail["code"] == "PLAN_VERSION_NOT_ACTIVE"


def test_prerequisites_must_pass_before_dependent_is_ready(
    db_session: Session,
) -> None:
    user, _, plan, version = _context(db_session, "day135-prerequisite")
    first = _task(
        db_session,
        version_id=version.id,
        user_id=user.id,
        position=1,
    )
    second = _task(
        db_session,
        version_id=version.id,
        user_id=user.id,
        position=2,
    )
    learning_task_service.add_task_prerequisite(
        db_session,
        plan_version_id=version.id,
        task_id=second.id,
        prerequisite_task_id=first.id,
        user_id=user.id,
    )
    _publish(
        db_session,
        plan_id=plan.id,
        version_id=version.id,
        user_id=user.id,
    )

    with pytest.raises(HTTPException) as blocked:
        _transition(
            db_session,
            task=second,
            user_id=user.id,
            target=TaskStatus.READY,
        )
    assert blocked.value.status_code == 409
    assert blocked.value.detail["code"] == "TASK_PREREQUISITES_INCOMPLETE"

    for target in (
        TaskStatus.READY,
        TaskStatus.IN_PROGRESS,
        TaskStatus.SUBMITTED,
        TaskStatus.PASSED,
    ):
        first = _transition(
            db_session,
            task=first,
            user_id=user.id,
            target=target,
        )

    second = _transition(
        db_session,
        task=second,
        user_id=user.id,
        target=TaskStatus.READY,
    )
    assert second.status == TaskStatus.READY.value


def test_owner_scope_and_task_version_scope_are_hidden(db_session: Session) -> None:
    owner, _, plan, version = _context(db_session, "day135-owner")
    other, _, _, _ = _context(db_session, "day135-other")
    task = _task(
        db_session,
        version_id=version.id,
        user_id=owner.id,
        position=1,
    )
    _publish(
        db_session,
        plan_id=plan.id,
        version_id=version.id,
        user_id=owner.id,
    )

    with pytest.raises(HTTPException) as owner_error:
        _transition(
            db_session,
            task=task,
            user_id=other.id,
            target=TaskStatus.READY,
        )
    assert owner_error.value.status_code == 404
    assert owner_error.value.detail["code"] == "PLAN_VERSION_NOT_FOUND"

    with pytest.raises(HTTPException) as task_error:
        learning_task_service.transition_task_status(
            db_session,
            plan_version_id=version.id,
            task_id=task.id + 100_000,
            user_id=owner.id,
            target_status=TaskStatus.READY,
        )
    assert task_error.value.status_code == 404
    assert task_error.value.detail["code"] == "LEARNING_TASK_NOT_FOUND"


def test_invalid_skip_and_passed_terminal_are_rejected(db_session: Session) -> None:
    user, _, plan, version = _context(db_session, "day135-invalid")
    task = _task(
        db_session,
        version_id=version.id,
        user_id=user.id,
        position=1,
    )
    _publish(
        db_session,
        plan_id=plan.id,
        version_id=version.id,
        user_id=user.id,
    )

    with pytest.raises(HTTPException) as skip_error:
        _transition(
            db_session,
            task=task,
            user_id=user.id,
            target=TaskStatus.IN_PROGRESS,
        )
    assert skip_error.value.status_code == 409
    assert skip_error.value.detail["code"] == "TASK_STATUS_TRANSITION_INVALID"

    for target in (
        TaskStatus.READY,
        TaskStatus.IN_PROGRESS,
        TaskStatus.SUBMITTED,
        TaskStatus.PASSED,
    ):
        task = _transition(
            db_session,
            task=task,
            user_id=user.id,
            target=target,
        )

    with pytest.raises(HTTPException) as terminal_error:
        _transition(
            db_session,
            task=task,
            user_id=user.id,
            target=TaskStatus.IN_PROGRESS,
        )
    assert terminal_error.value.status_code == 409
    assert terminal_error.value.detail["code"] == "TASK_STATUS_TRANSITION_INVALID"


def test_repository_compare_and_set_rejects_stale_expected_status(
    db_session: Session,
) -> None:
    user, _, _, version = _context(db_session, "day135-cas-repository")
    task = _task(
        db_session,
        version_id=version.id,
        user_id=user.id,
        position=1,
    )

    assert compare_and_set_task_status(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        expected_status=TaskStatus.DRAFT.value,
        target_status=TaskStatus.READY.value,
        completed_at=None,
    )
    db_session.commit()

    assert not compare_and_set_task_status(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        expected_status=TaskStatus.DRAFT.value,
        target_status=TaskStatus.IN_PROGRESS.value,
        completed_at=None,
    )
    db_session.rollback()
    db_session.refresh(task)
    assert task.status == TaskStatus.READY.value


def test_service_reports_compare_and_set_conflict_and_rolls_back(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, _, plan, version = _context(db_session, "day135-cas-service")
    task = _task(
        db_session,
        version_id=version.id,
        user_id=user.id,
        position=1,
    )
    _publish(
        db_session,
        plan_id=plan.id,
        version_id=version.id,
        user_id=user.id,
    )

    def reject_update(*_: object, **__: object) -> bool:
        return False

    monkeypatch.setattr(
        learning_task_service,
        "compare_and_set_task_status",
        reject_update,
    )

    with pytest.raises(HTTPException) as conflict:
        _transition(
            db_session,
            task=task,
            user_id=user.id,
            target=TaskStatus.READY,
        )
    assert conflict.value.status_code == 409
    assert conflict.value.detail["code"] == "TASK_STATUS_CONFLICT"

    db_session.refresh(task)
    assert task.status == TaskStatus.DRAFT.value
    assert task.completed_at is None
