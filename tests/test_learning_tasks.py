from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskPrerequisite
from app.models.user import User
from app.schemas.learning_plan import PlanCreate, PlanReject, PlanVersionCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import learning_plan_service, learning_task_service


def _context(
    db_session: Session,
    username: str,
) -> tuple[User, LearningProject, LearningPlan, PlanVersion]:
    user = User(username=username, password_hash="day134-test-placeholder")
    db_session.add(user)
    db_session.flush()
    project = LearningProject(
        user_id=user.id,
        name=f"{username} project",
        goal="build daily learning tasks",
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
            goal="complete the learning path",
            content={},
        ),
    )
    return user, project, plan, version


def _payload(
    position: int,
    *,
    scheduled_date: date | None = None,
    title: str | None = None,
) -> LearningTaskCreate:
    return LearningTaskCreate(
        position=position,
        scheduled_date=scheduled_date,
        title=title or f"Task {position}",
        objective=f"Objective {position}",
        instructions=f"Instructions {position}",
        steps=[f"Step {position}.1", f"Step {position}.2"],
        estimated_minutes=45,
        deliverable=f"Deliverable {position}",
        acceptance_criteria=[f"Criterion {position}"],
    )


def _task(
    db_session: Session,
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


def test_create_task_uses_draft_status_and_structured_fields(db_session) -> None:
    user, _, _, version = _context(db_session, "day134-create")
    task = learning_task_service.create_task(
        db_session,
        plan_version_id=version.id,
        user_id=user.id,
        payload=_payload(
            1,
            scheduled_date=date(2026, 9, 2),
            title="Read the parser",
        ),
    )

    assert task.plan_version_id == version.id
    assert task.position == 1
    assert task.scheduled_date == date(2026, 9, 2)
    assert task.status == "DRAFT"
    assert task.completed_at is None
    assert task.steps == ["Step 1.1", "Step 1.2"]
    assert task.acceptance_criteria == ["Criterion 1"]


@pytest.mark.parametrize(
    "changes",
    [
        {"position": 0},
        {"title": " "},
        {"objective": " "},
        {"instructions": " "},
        {"steps": []},
        {"steps": [" "]},
        {"estimated_minutes": 0},
        {"estimated_minutes": 1441},
        {"deliverable": " "},
        {"acceptance_criteria": []},
        {"acceptance_criteria": [" "]},
    ],
)
def test_task_schema_validation(changes: dict[str, object]) -> None:
    values = _payload(1).model_dump()
    values.update(changes)
    with pytest.raises(ValidationError):
        LearningTaskCreate(**values)


def test_list_tasks_orders_date_then_position_with_unscheduled_last(db_session) -> None:
    user, _, _, version = _context(db_session, "day134-order")
    learning_task_service.create_task(
        db_session,
        plan_version_id=version.id,
        user_id=user.id,
        payload=_payload(3),
    )
    learning_task_service.create_task(
        db_session,
        plan_version_id=version.id,
        user_id=user.id,
        payload=_payload(2, scheduled_date=date(2026, 9, 3)),
    )
    learning_task_service.create_task(
        db_session,
        plan_version_id=version.id,
        user_id=user.id,
        payload=_payload(1, scheduled_date=date(2026, 9, 2)),
    )

    tasks = learning_task_service.list_version_tasks(
        db_session,
        plan_version_id=version.id,
        user_id=user.id,
    )
    assert [task.position for task in tasks] == [1, 2, 3]


def test_duplicate_position_is_rejected_by_service_and_database(db_session) -> None:
    user, _, _, version = _context(db_session, "day134-position")
    _task(db_session, version.id, user.id, 1)

    with pytest.raises(HTTPException) as error:
        _task(db_session, version.id, user.id, 1)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "TASK_POSITION_CONFLICT"

    db_session.add(
        LearningTask(
            plan_version_id=version.id,
            position=1,
            title="duplicate",
            objective="duplicate",
            instructions="duplicate",
            steps=["duplicate"],
            estimated_minutes=10,
            deliverable="duplicate",
            acceptance_criteria=["duplicate"],
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_owner_scope_and_cross_version_task_lookup(db_session) -> None:
    owner, _, plan, version = _context(db_session, "day134-owner")
    other, _, _, _ = _context(db_session, "day134-other")
    first = _task(db_session, version.id, owner.id, 1)
    second_version = learning_plan_service.create_next_draft(
        db_session,
        plan_id=plan.id,
        user_id=owner.id,
        payload=PlanVersionCreate(goal="second", content={}),
    )
    foreign_task = _task(db_session, second_version.id, owner.id, 1)

    with pytest.raises(HTTPException) as owner_error:
        learning_task_service.list_version_tasks(
            db_session,
            plan_version_id=version.id,
            user_id=other.id,
        )
    assert owner_error.value.status_code == 404

    with pytest.raises(HTTPException) as cross_version:
        learning_task_service.add_task_prerequisite(
            db_session,
            plan_version_id=version.id,
            task_id=first.id,
            prerequisite_task_id=foreign_task.id,
            user_id=owner.id,
        )
    assert cross_version.value.status_code == 404
    assert cross_version.value.detail["code"] == "LEARNING_TASK_NOT_FOUND"


def test_published_and_rejected_versions_are_immutable(db_session) -> None:
    user, _, plan, published = _context(db_session, "day134-immutable")
    first = _task(db_session, published.id, user.id, 1)
    second = _task(db_session, published.id, user.id, 2)
    learning_plan_service.publish_version(
        db_session,
        plan_id=plan.id,
        version_id=published.id,
        user_id=user.id,
    )

    with pytest.raises(HTTPException) as create_error:
        _task(db_session, published.id, user.id, 3)
    assert create_error.value.status_code == 409

    with pytest.raises(HTTPException) as edge_error:
        learning_task_service.add_task_prerequisite(
            db_session,
            plan_version_id=published.id,
            task_id=second.id,
            prerequisite_task_id=first.id,
            user_id=user.id,
        )
    assert edge_error.value.status_code == 409

    rejected = learning_plan_service.create_next_draft(
        db_session,
        plan_id=plan.id,
        user_id=user.id,
        payload=PlanVersionCreate(goal="reject", content={}),
    )
    learning_plan_service.reject_draft(
        db_session,
        plan_id=plan.id,
        version_id=rejected.id,
        user_id=user.id,
        payload=PlanReject(reason="not useful"),
    )
    with pytest.raises(HTTPException) as rejected_error:
        _task(db_session, rejected.id, user.id, 1)
    assert rejected_error.value.status_code == 409


def test_prerequisite_idempotency_self_cycle_and_listing(db_session) -> None:
    user, _, _, version = _context(db_session, "day134-graph")
    first = _task(db_session, version.id, user.id, 1)
    second = _task(db_session, version.id, user.id, 2)
    third = _task(db_session, version.id, user.id, 3)

    edge, created = learning_task_service.add_task_prerequisite(
        db_session,
        plan_version_id=version.id,
        task_id=second.id,
        prerequisite_task_id=first.id,
        user_id=user.id,
    )
    duplicate, duplicate_created = learning_task_service.add_task_prerequisite(
        db_session,
        plan_version_id=version.id,
        task_id=second.id,
        prerequisite_task_id=first.id,
        user_id=user.id,
    )
    learning_task_service.add_task_prerequisite(
        db_session,
        plan_version_id=version.id,
        task_id=third.id,
        prerequisite_task_id=second.id,
        user_id=user.id,
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate.id == edge.id
    assert learning_task_service.get_task_prerequisite_ids(
        db_session,
        plan_version_id=version.id,
        task_id=second.id,
        user_id=user.id,
    ) == [first.id]

    with pytest.raises(HTTPException) as self_error:
        learning_task_service.add_task_prerequisite(
            db_session,
            plan_version_id=version.id,
            task_id=first.id,
            prerequisite_task_id=first.id,
            user_id=user.id,
        )
    assert self_error.value.status_code == 400

    with pytest.raises(HTTPException) as cycle_error:
        learning_task_service.add_task_prerequisite(
            db_session,
            plan_version_id=version.id,
            task_id=first.id,
            prerequisite_task_id=third.id,
            user_id=user.id,
        )
    assert cycle_error.value.status_code == 409
    assert cycle_error.value.detail["code"] == "TASK_PREREQUISITE_CYCLE"


def test_composite_foreign_keys_encode_same_version_rule() -> None:
    constraints = [
        constraint
        for constraint in TaskPrerequisite.__table__.foreign_key_constraints
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
    assert (
        ("prerequisite_task_id", "plan_version_id"),
        ("learning_tasks.id", "learning_tasks.plan_version_id"),
    ) in pairs


def test_database_rejects_invalid_status_completion_pair(db_session) -> None:
    user, _, _, version = _context(db_session, "day134-status-db")
    db_session.add(
        LearningTask(
            plan_version_id=version.id,
            position=1,
            title="invalid status",
            objective="invalid status",
            instructions="invalid status",
            steps=["step"],
            estimated_minutes=10,
            deliverable="deliverable",
            acceptance_criteria=["criterion"],
            status="PASSED",
            completed_at=None,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        LearningTask(
            plan_version_id=version.id,
            position=2,
            title="invalid completion",
            objective="invalid completion",
            instructions="invalid completion",
            steps=["step"],
            estimated_minutes=10,
            deliverable="deliverable",
            acceptance_criteria=["criterion"],
            status="DRAFT",
            completed_at=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
