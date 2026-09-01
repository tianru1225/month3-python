from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.user import User
from app.schemas.learning_plan import PlanCreate, PlanReject, PlanVersionCreate
from app.services import learning_plan_service


def _user_and_project(db_session, username: str) -> tuple[User, LearningProject]:
    user = User(username=username, password_hash="day133-test-placeholder")
    db_session.add(user)
    db_session.flush()
    project = LearningProject(
        user_id=user.id,
        name=f"{username} project",
        goal="build a traceable study plan",
        current_level="beginner",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(project)
    return user, project


def _first_payload() -> PlanCreate:
    return PlanCreate(
        name="Python foundations",
        goal="learn Python basics",
        content={"days": []},
    )


def _next_payload(goal: str = "learn FastAPI") -> PlanVersionCreate:
    return PlanVersionCreate(goal=goal, content={"days": ["api"]})


def test_create_plan_starts_with_version_one_draft(db_session) -> None:
    user, project = _user_and_project(db_session, "day133-create")
    plan, version = learning_plan_service.create_plan_with_first_draft(
        db_session,
        project_id=project.id,
        user_id=user.id,
        payload=_first_payload(),
    )

    assert plan.project_id == project.id
    assert version.plan_id == plan.id
    assert version.version_number == 1
    assert version.status == "DRAFT"
    assert version.is_current is False
    assert version.published_at is None


def test_next_draft_is_append_only(db_session) -> None:
    user, project = _user_and_project(db_session, "day133-next")
    plan, first = learning_plan_service.create_plan_with_first_draft(
        db_session, project_id=project.id, user_id=user.id, payload=_first_payload()
    )
    second = learning_plan_service.create_next_draft(
        db_session,
        plan_id=plan.id,
        user_id=user.id,
        payload=_next_payload(),
    )

    assert second.version_number == 2
    assert first.goal == "learn Python basics"
    versions = learning_plan_service.list_plan_versions(
        db_session, plan_id=plan.id, user_id=user.id
    )
    assert [item.version_number for item in versions] == [1, 2]


def test_publish_switches_current_without_mutating_old_content(db_session) -> None:
    user, project = _user_and_project(db_session, "day133-publish")
    plan, first = learning_plan_service.create_plan_with_first_draft(
        db_session, project_id=project.id, user_id=user.id, payload=_first_payload()
    )
    second = learning_plan_service.create_next_draft(
        db_session, plan_id=plan.id, user_id=user.id, payload=_next_payload()
    )

    published_first = learning_plan_service.publish_version(
        db_session, plan_id=plan.id, version_id=first.id, user_id=user.id
    )
    published_second = learning_plan_service.publish_version(
        db_session, plan_id=plan.id, version_id=second.id, user_id=user.id
    )
    db_session.refresh(first)

    assert published_first.status == "PUBLISHED"
    assert published_second.is_current is True
    assert first.status == "PUBLISHED"
    assert first.is_current is False
    assert first.content == {"days": []}

    current = learning_plan_service.get_current_published_version(
        db_session, plan_id=plan.id, user_id=user.id
    )
    assert current is not None
    assert current.id == second.id


def test_published_version_is_immutable(db_session) -> None:
    user, project = _user_and_project(db_session, "day133-immutable")
    plan, version = learning_plan_service.create_plan_with_first_draft(
        db_session, project_id=project.id, user_id=user.id, payload=_first_payload()
    )
    learning_plan_service.publish_version(
        db_session, plan_id=plan.id, version_id=version.id, user_id=user.id
    )

    with pytest.raises(HTTPException) as error:
        learning_plan_service.publish_version(
            db_session, plan_id=plan.id, version_id=version.id, user_id=user.id
        )
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "PLAN_VERSION_IMMUTABLE"

    with pytest.raises(HTTPException) as reject_error:
        learning_plan_service.reject_draft(
            db_session,
            plan_id=plan.id,
            version_id=version.id,
            user_id=user.id,
            payload=PlanReject(reason="too late"),
        )
    assert reject_error.value.status_code == 409

    assert not hasattr(learning_plan_service, "update_version")
    db_session.refresh(version)
    assert version.goal == "learn Python basics"
    assert version.content == {"days": []}


def test_reject_draft_keeps_old_published_version(db_session) -> None:
    user, project = _user_and_project(db_session, "day133-reject")
    plan, first = learning_plan_service.create_plan_with_first_draft(
        db_session, project_id=project.id, user_id=user.id, payload=_first_payload()
    )
    learning_plan_service.publish_version(
        db_session, plan_id=plan.id, version_id=first.id, user_id=user.id
    )
    second = learning_plan_service.create_next_draft(
        db_session, plan_id=plan.id, user_id=user.id, payload=_next_payload()
    )

    rejected = learning_plan_service.reject_draft(
        db_session,
        plan_id=plan.id,
        version_id=second.id,
        user_id=user.id,
        payload=PlanReject(reason="insufficient sources"),
    )
    current = learning_plan_service.get_current_published_version(
        db_session, plan_id=plan.id, user_id=user.id
    )

    assert rejected.status == "REJECTED"
    assert rejected.rejection_reason == "insufficient sources"
    assert current is not None
    assert current.id == first.id


def test_plan_and_version_are_owner_scoped(db_session) -> None:
    owner, project = _user_and_project(db_session, "day133-owner")
    other, _ = _user_and_project(db_session, "day133-other")
    plan, version = learning_plan_service.create_plan_with_first_draft(
        db_session, project_id=project.id, user_id=owner.id, payload=_first_payload()
    )

    with pytest.raises(HTTPException) as plan_error:
        learning_plan_service.list_plan_versions(
            db_session, plan_id=plan.id, user_id=other.id
        )
    assert plan_error.value.status_code == 404

    with pytest.raises(HTTPException) as version_error:
        learning_plan_service.publish_version(
            db_session, plan_id=plan.id, version_id=version.id, user_id=other.id
        )
    assert version_error.value.status_code == 404

    with pytest.raises(HTTPException) as create_error:
        learning_plan_service.create_plan_with_first_draft(
            db_session,
            project_id=project.id,
            user_id=other.id,
            payload=_first_payload(),
        )
    assert create_error.value.status_code == 404


def test_schema_validation() -> None:
    with pytest.raises(ValidationError):
        PlanCreate(name=" ", goal="valid")
    with pytest.raises(ValidationError):
        PlanVersionCreate(goal=" ")
    with pytest.raises(ValidationError):
        PlanReject(reason=" ")
    with pytest.raises(ValidationError):
        PlanCreate(name="valid", goal="valid", provider_name="x" * 81)
    with pytest.raises(ValidationError):
        PlanCreate(name="valid", goal="valid", provider_name="provider")
    with pytest.raises(ValidationError):
        PlanVersionCreate(goal="valid", source_kind="MODEL")

    model_payload = PlanVersionCreate(
        goal="valid",
        source_kind="MODEL",
        provider_name="openai-compatible",
        model_name="test-model",
    )
    assert model_payload.provider_name == "openai-compatible"


def test_database_rejects_two_current_versions(db_session) -> None:
    user, project = _user_and_project(db_session, "day133-unique")
    plan = LearningPlan(project_id=project.id, name="unique")
    db_session.add(plan)
    db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            PlanVersion(
                plan_id=plan.id,
                version_number=1,
                status="PUBLISHED",
                goal="one",
                content={},
                source_kind="MANUAL",
                published_at=now,
                confirmed_by_user_id=user.id,
                is_current=True,
            ),
            PlanVersion(
                plan_id=plan.id,
                version_number=2,
                status="PUBLISHED",
                goal="two",
                content={},
                source_kind="MANUAL",
                published_at=now,
                confirmed_by_user_id=user.id,
                is_current=True,
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_rejects_duplicate_version_number(db_session) -> None:
    _, project = _user_and_project(db_session, "day133-version-number")
    plan = LearningPlan(project_id=project.id, name="version numbers")
    db_session.add(plan)
    db_session.flush()
    db_session.add_all(
        [
            PlanVersion(
                plan_id=plan.id,
                version_number=1,
                goal="one",
                content={},
                source_kind="MANUAL",
            ),
            PlanVersion(
                plan_id=plan.id,
                version_number=1,
                goal="duplicate",
                content={},
                source_kind="MANUAL",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_rejects_invalid_model_identity(db_session) -> None:
    _, project = _user_and_project(db_session, "day133-model-identity")
    plan = LearningPlan(project_id=project.id, name="model identity")
    db_session.add(plan)
    db_session.flush()
    db_session.add(
        PlanVersion(
            plan_id=plan.id,
            version_number=1,
            goal="invalid model source",
            content={},
            source_kind="MODEL",
            provider_name=None,
            model_name=None,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    "values",
    [
        {
            "status": "DRAFT",
            "published_at": datetime.now(timezone.utc),
            "is_current": False,
        },
        {
            "status": "PUBLISHED",
            "published_at": datetime.now(timezone.utc),
            "confirmed_by_user_id": None,
            "is_current": True,
        },
        {
            "status": "REJECTED",
            "rejection_reason": None,
            "is_current": False,
        },
    ],
)
def test_database_rejects_inconsistent_state_fields(db_session, values) -> None:
    _, project = _user_and_project(db_session, f"day133-state-{values['status']}")
    plan = LearningPlan(project_id=project.id, name="state checks")
    db_session.add(plan)
    db_session.flush()
    version = PlanVersion(
        plan_id=plan.id,
        version_number=1,
        goal="valid",
        content={},
        source_kind="MANUAL",
        **values,
    )
    db_session.add(version)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_publish_rollback_restores_old_current(db_session, monkeypatch) -> None:
    user, project = _user_and_project(db_session, "day133-rollback")
    plan, first = learning_plan_service.create_plan_with_first_draft(
        db_session, project_id=project.id, user_id=user.id, payload=_first_payload()
    )
    learning_plan_service.publish_version(
        db_session, plan_id=plan.id, version_id=first.id, user_id=user.id
    )
    second = learning_plan_service.create_next_draft(
        db_session, plan_id=plan.id, user_id=user.id, payload=_next_payload()
    )
    second_id = second.id

    def fail_after_old_current_is_flushed():
        raise RuntimeError("forced publish failure")

    monkeypatch.setattr(
        learning_plan_service,
        "_now",
        fail_after_old_current_is_flushed,
    )
    with pytest.raises(RuntimeError, match="forced publish failure"):
        learning_plan_service.publish_version(
            db_session,
            plan_id=plan.id,
            version_id=second_id,
            user_id=user.id,
        )

    db_session.expire_all()
    current = learning_plan_service.get_current_published_version(
        db_session, plan_id=plan.id, user_id=user.id
    )
    assert current is not None and current.id == first.id
    persisted_second = db_session.get(PlanVersion, second_id)
    assert persisted_second is not None
    assert persisted_second.status == "DRAFT"
