import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.learning_project import LearningProject, ProjectStatus
from app.models.user import User


def _create_user(db_session, username: str = "project-owner") -> User:
    user = User(
        username=username,
        password_hash="test-password-hash",
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_learning_project_persists_owner_fields_and_defaults(db_session) -> None:
    user = _create_user(db_session)
    project = LearningProject(
        user_id=user.id,
        name="FastAPI 学习项目",
    )

    db_session.add(project)
    db_session.commit()

    saved = db_session.scalar(
        select(LearningProject).where(LearningProject.id == project.id)
    )

    assert saved is not None
    assert saved.user_id == user.id
    assert saved.name == "FastAPI 学习项目"
    assert saved.status == ProjectStatus.ACTIVE.value
    assert saved.created_at is not None
    assert saved.updated_at is not None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "UNKNOWN"),
    ],
)
def test_learning_project_rejects_invalid_database_values(
    db_session,
    field: str,
    value: object,
) -> None:
    user = _create_user(db_session, username=f"invalid-{field}-{value}")
    project = LearningProject(
        user_id=user.id,
        name="约束测试项目",
    )
    setattr(project, field, value)
    db_session.add(project)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_learning_project_supports_all_declared_statuses(db_session) -> None:
    user = _create_user(db_session, username="status-project-owner")

    for index, project_status in enumerate(ProjectStatus):
        project = LearningProject(
            user_id=user.id,
            name=f"状态项目-{index}",
            status=project_status.value,
        )
        db_session.add(project)

    db_session.commit()

    statuses = db_session.scalars(select(LearningProject.status)).all()
    assert set(statuses) == {item.value for item in ProjectStatus}