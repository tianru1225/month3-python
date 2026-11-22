"""Regression tests for the replacement of plan/version storage with one plan."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.learning_plan import LearningPlan
from app.models.learning_project import LearningProject
from app.models.user import User
from app.schemas.learning_plan import PlanCreate
from app.services import learning_plan_service


def context(db, suffix="plan"):
    user = User(username=suffix, password_hash="test-placeholder")
    db.add(user)
    db.flush()
    project = LearningProject(user_id=user.id, name=suffix)
    db.add(project)
    db.commit()
    return user, project


def test_one_plan_per_project_and_owner_boundary(db_session):
    user, project = context(db_session)
    plan = learning_plan_service.create_plan(
        db_session, project_id=project.id, user_id=user.id,
        payload=PlanCreate(),
    )
    assert plan.locked_at is None
    assert plan.project_id == project.id
    assert learning_plan_service.get_plan(
        db_session, plan_id=plan.id, user_id=user.id,
    ).id == plan.id
    with pytest.raises(HTTPException) as duplicate:
        learning_plan_service.create_plan(
            db_session, project_id=project.id, user_id=user.id,
            payload=PlanCreate(),
        )
    assert duplicate.value.detail["code"] == "PROJECT_PLAN_EXISTS"
    outsider, _ = context(db_session, "outsider")
    for operation in (
        lambda: learning_plan_service.get_plan(
            db_session, plan_id=plan.id, user_id=outsider.id,
        ),
        lambda: learning_plan_service.start_plan(
            db_session, plan_id=plan.id, user_id=outsider.id,
        ),
    ):
        with pytest.raises(HTTPException) as denied:
            operation()
        assert denied.value.status_code == 404
    db_session.add(LearningPlan(project_id=project.id, content={}))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_schema_removes_old_inputs_and_validates_model_identity():
    for payload in (
        {"goal": "Old goal"},
        {"name": "Old field"},
        {"source_kind": "MODEL"},
        {"provider_name": "provider"},
        {"model_name": "model"},
        {"provider_name": " ", "model_name": "model"},
        {"provider_name": "provider", "model_name": " "},
    ):
        with pytest.raises(ValidationError):
            PlanCreate(**payload)
    result = PlanCreate(
        provider_name=" provider ", model_name=" model ",
    )
    assert result.provider_name == "provider" and result.model_name == "model"
    manual_fixture = PlanCreate()
    assert manual_fixture.provider_name is None and manual_fixture.model_name is None
    assert "goal" not in result.model_dump() and "source_kind" not in result.model_dump()


@pytest.mark.parametrize(
    ("provider", "model"),
    [("provider", None), (None, "model"), (" ", "model"), ("provider", " ")],
)
def test_database_rejects_incomplete_model_identity(db_session, provider, model):
    _, project = context(db_session, "invalid-model")
    db_session.add(LearningPlan(
        project_id=project.id, content={}, provider_name=provider, model_name=model,
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_start_is_idempotent_and_commit_failure_rolls_back(db_session, monkeypatch):
    user, project = context(db_session, "lock")
    plan = learning_plan_service.create_plan(
        db_session, project_id=project.id, user_id=user.id,
        payload=PlanCreate(),
    )
    def fail_commit():
        raise RuntimeError("commit failed")
    with monkeypatch.context() as patch:
        patch.setattr(db_session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="commit failed"):
            learning_plan_service.start_plan(
                db_session, plan_id=plan.id, user_id=user.id,
            )
    db_session.expire_all()
    assert plan.locked_at is None
    learning_plan_service.start_plan(db_session, plan_id=plan.id, user_id=user.id)
    started = plan.locked_at
    learning_plan_service.start_plan(db_session, plan_id=plan.id, user_id=user.id)
    assert plan.locked_at == started and started is not None


def test_create_failure_does_not_leave_partial_plan(db_session, monkeypatch):
    user, project = context(db_session, "create-rollback")
    original_add = learning_plan_service.add_plan
    def fail_after_flush(*args, **kwargs):
        original_add(*args, **kwargs)
        raise RuntimeError("after insert")
    monkeypatch.setattr(learning_plan_service, "add_plan", fail_after_flush)
    with pytest.raises(RuntimeError, match="after insert"):
        learning_plan_service.create_plan(
            db_session, project_id=project.id, user_id=user.id,
            payload=PlanCreate(),
        )
    assert db_session.scalar(select(LearningPlan)) is None