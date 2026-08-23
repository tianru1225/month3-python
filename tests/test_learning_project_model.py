from datetime import date

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
        goal="完成一个带认证和数据库的 FastAPI 服务",
        current_level="已有 Python 基础",
        deadline=date(2026, 10, 31),
        expected_outcome="能够独立实现并部署后端 API",
    )

    db_session.add(project)
    db_session.commit()

    saved = db_session.scalar(
        select(LearningProject).where(LearningProject.id == project.id)
    )

    assert saved is not None
    assert saved.user_id == user.id
    assert saved.name == "FastAPI 学习项目"
    assert saved.goal == "完成一个带认证和数据库的 FastAPI 服务"
    assert saved.current_level == "已有 Python 基础"
    assert saved.deadline == date(2026, 10, 31)
    assert saved.daily_minutes == 60
    assert saved.weekly_days == 7
    assert saved.expected_outcome == "能够独立实现并部署后端 API"
    assert saved.status == ProjectStatus.ACTIVE.value
    assert saved.created_at is not None
    assert saved.updated_at is not None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "UNKNOWN"),
        ("daily_minutes", 0),
        ("daily_minutes", 1441),
        ("weekly_days", 0),
        ("weekly_days", 8),
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
        goal="测试数据库约束",
        current_level="入门",
    )
    setattr(project, field, value)
    db_session.add(project)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_learning_project_allows_nullable_optional_fields(db_session) -> None:
    user = _create_user(db_session, username="nullable-project-owner")
    project = LearningProject(
        user_id=user.id,
        name="可选字段测试",
        goal="验证截止日期和期望成果可以为空",
        current_level="入门",
        deadline=None,
        expected_outcome=None,
    )

    db_session.add(project)
    db_session.commit()

    assert project.deadline is None
    assert project.expected_outcome is None


def test_learning_project_supports_all_declared_statuses(db_session) -> None:
    user = _create_user(db_session, username="status-project-owner")

    for index, project_status in enumerate(ProjectStatus):
        project = LearningProject(
            user_id=user.id,
            name=f"状态项目-{index}",
            goal="验证项目状态约束",
            current_level="入门",
            status=project_status.value,
        )
        db_session.add(project)

    db_session.commit()

    statuses = db_session.scalars(select(LearningProject.status)).all()
    assert set(statuses) == {item.value for item in ProjectStatus}
