import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskPrerequisite, TaskStatus
from app.models.user import User
from app.schemas.learning_plan import PlanCreate, PlanVersionCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import learning_plan_service, learning_task_service


def context(
    db: Session, suffix: str
) -> tuple[User, LearningProject, LearningPlan, PlanVersion]:
    user = User(username=f"{suffix}-user", password_hash="day140-test-placeholder")
    db.add(user)
    db.flush()
    project = LearningProject(
        user_id=user.id,
        name=f"{suffix}-project",
        goal="verify transaction boundaries",
        current_level="beginner",
    )
    db.add(project)
    db.flush()
    plan = LearningPlan(project_id=project.id, name=f"{suffix}-plan")
    db.add(plan)
    db.flush()
    version = PlanVersion(
        plan_id=plan.id,
        version_number=1,
        status="DRAFT",
        goal="verify transactions",
        content={"tasks": []},
        source_kind="MANUAL",
        is_current=False,
    )
    db.add(version)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    db.refresh(plan)
    db.refresh(version)
    return user, project, plan, version


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


def test_create_plan_rolls_back_if_version_insert_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(username="day140-plan-rollback-user", password_hash="placeholder")
    db_session.add(user)
    db_session.flush()
    project = LearningProject(
        user_id=user.id,
        name="day140-plan-rollback-project",
        goal="transaction rollback",
        current_level="beginner",
    )
    db_session.add(project)
    db_session.commit()

    def fail_add_version(*args: object, **kwargs: object) -> PlanVersion:
        raise RuntimeError("version insert failed")

    monkeypatch.setattr(learning_plan_service, "add_version", fail_add_version)
    with pytest.raises(RuntimeError, match="version insert failed"):
        learning_plan_service.create_plan_with_first_draft(
            db_session,
            project_id=project.id,
            user_id=user.id,
            payload=PlanCreate(
                name="should roll back", goal="should roll back", content={}
            ),
        )

    assert (
        db_session.scalar(
            select(LearningPlan).where(LearningPlan.project_id == project.id)
        )
        is None
    )
    assert db_session.scalar(select(PlanVersion)) is None


def test_create_next_draft_rolls_back_if_commit_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _, plan, first = context(db_session, "next-draft")
    original_commit = db_session.commit

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        learning_plan_service.create_next_draft(
            db_session,
            plan_id=plan.id,
            user_id=user.id,
            payload=PlanVersionCreate(goal="next", content={"tasks": ["next"]}),
        )
    monkeypatch.setattr(db_session, "commit", original_commit)
    db_session.expire_all()
    assert db_session.get(PlanVersion, first.id) is not None
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PlanVersion)
            .where(PlanVersion.plan_id == plan.id)
        )
        == 1
    )


def test_publish_rolls_back_if_commit_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _, plan, version = context(db_session, "publish")
    original_commit = db_session.commit

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        learning_plan_service.publish_version(
            db_session, plan_id=plan.id, version_id=version.id, user_id=user.id
        )
    monkeypatch.setattr(db_session, "commit", original_commit)
    db_session.expire_all()
    stored = db_session.get(PlanVersion, version.id)
    assert stored is not None
    assert stored.status == "DRAFT"
    assert stored.is_current is False
    assert stored.published_at is None
    assert stored.confirmed_by_user_id is None


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
            plan_version_id=version.id,
            user_id=user.id,
            payload=task_payload(1),
        )
    assert (
        db_session.scalar(
            select(LearningTask).where(LearningTask.plan_version_id == version.id)
        )
        is None
    )


def test_prerequisite_write_rolls_back_if_commit_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _, _, version = context(db_session, "edge")
    first = learning_task_service.create_task(
        db_session, plan_version_id=version.id, user_id=user.id, payload=task_payload(1)
    )
    second = learning_task_service.create_task(
        db_session, plan_version_id=version.id, user_id=user.id, payload=task_payload(2)
    )
    original_commit = db_session.commit

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        learning_task_service.add_task_prerequisite(
            db_session,
            plan_version_id=version.id,
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
        db_session, plan_version_id=version.id, user_id=user.id, payload=task_payload(1)
    )
    learning_plan_service.publish_version(
        db_session, plan_id=plan.id, version_id=version.id, user_id=user.id
    )
    original_commit = db_session.commit

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        learning_task_service.transition_task_status(
            db_session,
            plan_version_id=version.id,
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
        plan_version_id=version.id,
        user_id=user.id,
        payload=task_payload(1),
    )
    assert calls == 1
