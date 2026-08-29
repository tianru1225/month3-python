from contextlib import nullcontext

import pytest
from redis.exceptions import ConnectionError

from app.models.material import MaterialVersion, ParseStatus
from app.services import material_service
from app.tasks import material_jobs


class FakeQueue:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.calls: list[dict] = []

    def enqueue(self, function, *args, **options):
        if self.unavailable:
            raise ConnectionError("queue unavailable")
        self.calls.append(
            {
                "function": function,
                "version_id": args[0],
                "job_id": args[1],
                "rq_job_id": options["job_id"],
            }
        )


@pytest.fixture(autouse=True)
def isolated_material_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        material_service,
        "MATERIAL_STORAGE_DIR",
        tmp_path / "materials",
    )


def _register_and_login(client, username: str) -> dict[str, str]:
    password = "day130-job-password"
    assert (
        client.post(
            "/users",
            json={"username": username, "password": password},
        ).status_code
        == 201
    )
    login = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _upload(client, headers: dict[str, str]) -> dict:
    response = client.post(
        "/materials",
        headers=headers,
        data={"name": "异步资料"},
        files={"file": ("async.md", b"# Async\n\nbody\n", "text/markdown")},
    )
    assert response.status_code == 201
    return response.json()


def _path(body: dict) -> str:
    return f"/materials/{body['material_id']}/versions/{body['version_id']}/parse"


def test_first_enqueue_is_202_and_duplicate_is_idempotent(
    client,
    db_session,
    monkeypatch,
) -> None:
    headers = _register_and_login(client, "job-idempotent")
    body = _upload(client, headers)
    queue = FakeQueue()
    monkeypatch.setattr(material_service.material_queue, "enqueue", queue.enqueue)

    first = client.post(_path(body), headers=headers)
    duplicate = client.post(_path(body), headers=headers)

    assert first.status_code == 202
    assert duplicate.status_code == 200
    assert first.json()["job_id"] == duplicate.json()["job_id"]
    assert first.json()["parse_status"] == ParseStatus.QUEUED.value
    assert len(queue.calls) == 1
    assert queue.calls[0]["job_id"] == queue.calls[0]["rq_job_id"]

    version = db_session.get(MaterialVersion, body["version_id"])
    assert version is not None
    assert version.parse_job_id == first.json()["job_id"]


def test_get_status_uses_postgresql_and_requires_owner(client, monkeypatch) -> None:
    owner = _register_and_login(client, "job-status-owner")
    other = _register_and_login(client, "job-status-other")
    body = _upload(client, owner)
    queue = FakeQueue()
    monkeypatch.setattr(material_service.material_queue, "enqueue", queue.enqueue)
    queued = client.post(_path(body), headers=owner)
    assert queued.status_code == 202

    status_response = client.get(_path(body), headers=owner)
    forbidden = client.get(_path(body), headers=other)

    assert status_response.status_code == 200
    assert status_response.json()["parse_status"] == ParseStatus.QUEUED.value
    assert status_response.json()["parse_job_id"] == queued.json()["job_id"]
    assert forbidden.status_code == 404
    assert forbidden.json()["detail"]["code"] == "MATERIAL_VERSION_NOT_FOUND"


def test_queue_failure_restores_previous_state(
    client,
    db_session,
    monkeypatch,
) -> None:
    headers = _register_and_login(client, "job-queue-failure")
    body = _upload(client, headers)
    queue = FakeQueue(unavailable=True)
    monkeypatch.setattr(material_service.material_queue, "enqueue", queue.enqueue)

    response = client.post(_path(body), headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MATERIAL_QUEUE_UNAVAILABLE"
    version = db_session.get(MaterialVersion, body["version_id"])
    assert version is not None
    assert version.parse_status == ParseStatus.UPLOADED.value
    assert version.parse_job_id is None


def test_failed_version_can_enqueue_new_job(
    client,
    db_session,
    monkeypatch,
) -> None:
    headers = _register_and_login(client, "job-failed-retry")
    body = _upload(client, headers)
    version = db_session.get(MaterialVersion, body["version_id"])
    assert version is not None
    version.parse_status = ParseStatus.FAILED.value
    version.parse_job_id = "old-job"
    version.parser_name = "old-parser"
    version.parser_version = "old-version"
    version.parse_error_code = "MATERIAL_CONTENT_EMPTY"
    db_session.commit()

    queue = FakeQueue()
    monkeypatch.setattr(material_service.material_queue, "enqueue", queue.enqueue)
    response = client.post(_path(body), headers=headers)

    assert response.status_code == 202
    assert response.json()["job_id"] != "old-job"
    assert version.parse_status == ParseStatus.QUEUED.value
    assert version.parser_name is None
    assert version.parser_version is None
    assert version.parse_error_code is None


def test_ready_version_is_not_requeued(client, db_session, monkeypatch) -> None:
    headers = _register_and_login(client, "job-ready-idempotent")
    body = _upload(client, headers)
    version = db_session.get(MaterialVersion, body["version_id"])
    assert version is not None
    version.parse_status = ParseStatus.READY.value
    version.parse_job_id = "ready-job"
    db_session.commit()
    queue = FakeQueue()
    monkeypatch.setattr(material_service.material_queue, "enqueue", queue.enqueue)

    response = client.post(_path(body), headers=headers)

    assert response.status_code == 200
    assert response.json()["job_id"] == "ready-job"
    assert queue.calls == []


def test_stale_worker_job_is_ignored(
    client,
    db_session,
    monkeypatch,
) -> None:
    headers = _register_and_login(client, "job-stale-worker")
    body = _upload(client, headers)
    version = db_session.get(MaterialVersion, body["version_id"])
    assert version is not None
    version.parse_status = ParseStatus.QUEUED.value
    version.parse_job_id = "current-job"
    db_session.commit()
    monkeypatch.setattr(
        material_jobs,
        "SessionLocal",
        lambda: nullcontext(db_session),
    )

    result = material_jobs.parse_material_version_job(
        version.id,
        "stale-job",
    )

    assert result == "ignored:stale_job"
    assert version.parse_status == ParseStatus.QUEUED.value
    assert version.parse_job_id == "current-job"


def test_parse_routes_require_bearer(client) -> None:
    responses = [
        client.post("/materials/1/versions/1/parse"),
        client.get("/materials/1/versions/1/parse"),
    ]
    assert [response.status_code for response in responses] == [401, 401]
    assert [response.json()["detail"]["code"] for response in responses] == [
        "AUTH_REQUIRED",
        "AUTH_REQUIRED",
    ]
