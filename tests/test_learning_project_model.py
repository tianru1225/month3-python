from sqlalchemy import select

from app.models.learning_project import LearningProject
from app.models.user import User


def test_learning_project_persists_owner_name_and_timestamps(db_session) -> None:
    user = User(username="project-owner", password_hash="test-password-hash")
    db_session.add(user)
    db_session.flush()
    project = LearningProject(user_id=user.id, name="FastAPI 学习项目")
    db_session.add(project)
    db_session.commit()

    saved = db_session.scalar(
        select(LearningProject).where(LearningProject.id == project.id)
    )
    assert saved is not None
    assert saved.user_id == user.id
    assert saved.name == "FastAPI 学习项目"
    assert saved.created_at is not None
    assert saved.updated_at is not None
    assert saved.deleted_at is None