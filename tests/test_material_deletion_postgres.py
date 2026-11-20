import os
from threading import Event, Thread
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.learning_project import LearningProject
from app.models.user import User
from app.services import material_management_service as management
from app.services import material_service, project_material_service
from app.tasks import material_jobs


@pytest.fixture
def postgres_context(tmp_path, monkeypatch):
    url = os.environ.get("MATERIAL_DELETION_TEST_URL")
    if not url:
        pytest.skip("requires an isolated migrated PostgreSQL database")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "material_delete_check":
        raise RuntimeError("Only the disposable material_delete_check database is allowed")
    engine = create_engine(url)
    monkeypatch.setattr(material_service, "MATERIAL_STORAGE_DIR", tmp_path / "materials")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar_one() == "material_delete_check"
    with Session(engine) as db:
        user = User(username="cleanup-" + uuid4().hex[:20], password_hash="not-for-login")
        db.add(user)
        db.flush()
        project = LearningProject(
            user_id=user.id, name="Race check",
        )
        db.add(project)
        db.commit()
        user_id, project_id = user.id, project.id
        item = material_service.upload_material_or_raise(
            db, user_id=user_id, name="Race notes", description=None,
            filename="race.md", content_type="text/markdown", content=b"# Race\n\nbody\n",
        )
    try:
        yield engine, user_id, project_id, item
    finally:
        engine.dispose()


def pause_first_commit(engine, writer, competitors):
    entered, release = Event(), Event()
    failures = []

    class PausedSession(Session):
        paused = False

        def commit(self):
            if not self.paused:
                self.paused = True
                entered.set()
                if not release.wait(10):
                    raise TimeoutError("test failed to release pending transaction")
            super().commit()

    def work():
        try:
            with PausedSession(bind=engine) as db:
                writer(db)
        except BaseException as exc:
            failures.append(exc)

    thread = Thread(target=work, daemon=True)
    thread.start()
    try:
        assert entered.wait(5), failures
        for operation in competitors:
            with Session(engine) as db:
                db.execute(text("SET LOCAL lock_timeout = '300ms'"))
                with pytest.raises(OperationalError) as caught:
                    operation(db)
                assert getattr(caught.value.orig, "sqlstate", None) == "55P03"
                db.rollback()
    finally:
        release.set()
        thread.join(timeout=10)
    assert not thread.is_alive()
    assert not failures, failures


def test_delete_serializes_with_binding_and_enqueue(postgres_context):
    engine, user_id, project_id, item = postgres_context

    def remove(db):
        management.delete_material_or_raise(
            db, material_id=item.material_id, user_id=user_id,
        )

    def bind(db):
        project_material_service.bind_material_or_raise(
            db, project_id=project_id, material_id=item.material_id, user_id=user_id,
        )

    def enqueue(db):
        material_service.enqueue_material_parse_or_raise(
            db, user_id=user_id, material_id=item.material_id,
        )

    pause_first_commit(engine, remove, [bind, enqueue])
    for operation in (bind, enqueue):
        with Session(engine) as db:
            with pytest.raises(HTTPException) as caught:
                operation(db)
            assert caught.value.status_code == 404


def test_enqueue_claim_blocks_delete_until_worker_finishes(
    postgres_context, monkeypatch,
):
    engine, user_id, _, item = postgres_context
    jobs = []

    class LocalQueue:
        def enqueue(self, function, material_id, task_job_id, **options):
            jobs.append((material_id, task_job_id))

    def enqueue(db):
        material_service.enqueue_material_parse_or_raise(
            db, user_id=user_id, material_id=item.material_id,
            queue=LocalQueue(),
        )

    def remove(db):
        management.delete_material_or_raise(
            db, material_id=item.material_id, user_id=user_id,
        )

    pause_first_commit(engine, enqueue, [remove])
    with Session(engine) as db:
        with pytest.raises(HTTPException) as caught:
            remove(db)
        assert caught.value.status_code == 409
    monkeypatch.setattr(material_jobs, "SessionLocal", lambda: Session(engine))
    material_id, job_id = jobs[0]
    assert material_jobs.parse_material_job(material_id, job_id) == "READY"
    with Session(engine) as db:
        remove(db)
    assert material_jobs.parse_material_job(material_id, job_id) == "ignored:not_found"