import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskPrerequisite, TaskStatus
from app.models.user import User
from app.schemas.learning_plan import PlanCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import learning_plan_service, learning_task_service


def context(
    db: Session, suffix: str
) -> tuple[User, LearningProject, LearningPlan, LearningPlan]:
    user = User(username=f"{suffix}-user", password_hash="test-placeholder")
    db.add(user)
    db.flush()
    project = LearningProject(user_id=user.id, name=f"{suffix}-project")
    db.add(project)
    db.commit()
    plan = learning_plan_service.create_plan(
        db, project_id=project.id, user_id=user.id,
        payload=PlanCreate(),
    )
    return user, project, plan, plan

def task_payload(position: int) -> LearningTaskCreate:
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


def test_create_task_rolls_back_if_repository_insert_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _, _, version = context(db_session, "task")

    def fail_add_task(*args: object, **kwargs: object) -> LearningTask:
        raise RuntimeError("task insert failed")

    monkeypatch.setattr(learning_task_service, "add_task", fail_add_task)
    with pytest.raises(RuntimeError, match="task insert failed"):
        learning_task_service.create_task(
            db_session,
            plan_id=version.id,
            user_id=user.id,
            payload=task_payload(1),
        )
    assert (
        db_session.scalar(
            select(LearningTask).where(LearningTask.plan_id == version.id)
        )
        is None
    )


def test_prerequisite_write_rolls_back_if_commit_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _, _, version = context(db_session, "edge")
    first = learning_task_service.create_task(
        db_session, plan_id=version.id, user_id=user.id, payload=task_payload(1)
    )
    second = learning_task_service.create_task(
        db_session, plan_id=version.id, user_id=user.id, payload=task_payload(2)
    )
    original_commit = db_session.commit

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        learning_task_service.add_task_prerequisite(
            db_session,
            plan_id=version.id,
            task_id=second.id,
            prerequisite_task_id=first.id,
            user_id=user.id,
        )
    monkeypatch.setattr(db_session, "commit", original_commit)
    db_session.expire_all()
    assert db_session.scalar(select(TaskPrerequisite)) is None


def test_status_transition_rolls_back_if_commit_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _, plan, version = context(db_session, "status")
    task = learning_task_service.create_task(
        db_session, plan_id=version.id, user_id=user.id, payload=task_payload(1)
    )
    learning_plan_service.start_plan(
        db_session, plan_id=plan.id, user_id=user.id
    )
    original_commit = db_session.commit

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        learning_task_service.transition_task_status(
            db_session,
            plan_id=version.id,
            task_id=task.id,
            user_id=user.id,
            target_status=TaskStatus.READY,
        )
    monkeypatch.setattr(db_session, "commit", original_commit)
    db_session.expire_all()
    stored = db_session.get(LearningTask, task.id)
    assert stored is not None
    assert stored.status == TaskStatus.DRAFT.value
    assert stored.completed_at is None


def test_normal_service_write_still_commits_once(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _, _, version = context(db_session, "commit-count")
    original_commit = db_session.commit
    calls = 0

    def counted_commit() -> None:
        nonlocal calls
        calls += 1
        original_commit()

    monkeypatch.setattr(db_session, "commit", counted_commit)
    learning_task_service.create_task(
        db_session,
        plan_id=version.id,
        user_id=user.id,
        payload=task_payload(1),
    )
    assert calls == 1