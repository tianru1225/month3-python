import json
from contextlib import nullcontext
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.knowledge import KnowledgeNodeSource
from app.models.material import Material
from app.models.project_material import ProjectMaterialBinding
from app.models.user import User
from app.repositories.material_repository import (
    mark_material_failed, mark_material_parsing, mark_material_queued,
    restore_parse_queue_state,
)
from app.schemas.learning_plan import PlanCreate
from app.services import knowledge_service, learning_plan_service, material_service
from app.tasks import material_jobs


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    root = tmp_path / "materials"
    monkeypatch.setattr(material_service, "MATERIAL_STORAGE_DIR", root)
    monkeypatch.setattr(knowledge_service, "MATERIAL_STORAGE_DIR", root)
    return root


def login(client, name):
    password = "material-cleanup-test-password"
    assert client.post("/users", json={"username": name, "password": password}).status_code == 201
    result = client.post("/auth/login", json={"username": name, "password": password})
    assert result.status_code == 200
    return {"Authorization": "Bearer " + result.json()["access_token"]}


def upload(client, headers):
    result = client.post(
        "/materials", headers=headers, data={"name": "Cleanup notes"},
        files={"file": ("notes.md", b"# Notes\n\nKeep useful history.\n", "text/markdown")},
    )
    assert result.status_code == 201
    return result.json()


def project(client, headers):
    result = client.post("/projects", headers=headers, json={"name": "Cleanup project"})
    assert result.status_code == 201
    return result.json()["id"]


def parsed_version(db, item):
    version = db.get(Material, item["material_id"])
    assert version is not None
    mark_material_queued(db, version, job_id="parse-for-deletion-test")
    material_service.process_material(db, version)
    assert version.parse_status == "READY"
    return version


def test_management_is_owner_scoped_and_removes_files_with_safe_paths(
    client, db_session, storage,
):
    owner = login(client, "cleanup-owner")
    other = login(client, "cleanup-other")
    item = upload(client, owner)
    second = upload(client, owner)
    foreign = upload(client, other)
    path = f"/materials/{item['material_id']}"
    assert client.get("/materials").status_code == 401
    assert client.delete(path).status_code == 401
    assert client.delete(path, headers=other).status_code == 404
    assert client.delete("/materials/999999", headers=owner).status_code == 404
    first_page = client.get("/materials?limit=1", headers=owner)
    assert first_page.status_code == 200
    assert first_page.json()["items"][0]["material_id"] == second["material_id"]
    cursor = first_page.json()["next_before_id"]
    page = client.get(f"/materials?limit=1&before_id={cursor}", headers=owner).json()
    assert [value["material_id"] for value in page["items"]] == [item["material_id"]]
    assert page["next_before_id"] is None

    version = parsed_version(db_session, item)
    original = storage / version.storage_object_key
    parsed = storage / version.parsed_content_location
    sources = parsed.with_suffix(".sources.json")
    assert all(file.exists() for file in (original, parsed, sources))
    response = client.delete(path, headers=owner)
    assert response.status_code == 204 and response.content == b""
    assert not any(file.exists() for file in (original, parsed, sources))
    assert db_session.get(Material, item["material_id"]) is None
    assert client.delete(path, headers=owner).status_code == 404
    assert db_session.get(Material, foreign["material_id"]) is not None

    invalid = db_session.get(Material, second["material_id"])
    invalid.storage_object_key = "../do-not-delete.md"
    db_session.commit()
    sentinel = storage.parent / "do-not-delete.md"
    sentinel.write_text("keep", encoding="utf-8")
    rejected = client.delete(f"/materials/{second['material_id']}", headers=owner)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "MATERIAL_STORAGE_LAYOUT_INVALID"
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert db_session.get(Material, second["material_id"]).deletion_started_at is None


def test_bindings_and_learning_history_prevent_permanent_deletion(
    client, db_session, storage,
):
    headers = login(client, "cleanup-history")
    item = upload(client, headers)
    version = parsed_version(db_session, item)
    projects = [project(client, headers), project(client, headers)]
    for project_id in projects:
        assert client.post(
            f"/projects/{project_id}/materials/{item['material_id']}", headers=headers,
        ).status_code == 201
    path = f"/materials/{item['material_id']}"
    assert client.delete(path, headers=headers).status_code == 409
    assert client.delete(
        f"/projects/{projects[0]}/materials/{item['material_id']}", headers=headers,
    ).status_code == 204
    assert client.delete(path, headers=headers).status_code == 409

    node = client.post(
        f"/projects/{projects[1]}/knowledge-nodes", headers=headers,
        json={"title": "Notes", "description": "Keep source history"},
    )
    assert node.status_code == 201
    source_map = json.loads((storage / version.source_metadata["sources_path"]).read_text(encoding="utf-8"))
    source = source_map["blocks"][0]["source"]
    added = client.post(
        f"/projects/{projects[1]}/knowledge-nodes/{node.json()['id']}/sources",
        headers=headers, json={
            "material_id": version.id, "block_index": 0,
            "line_start": source["line_start"], "line_end": source["line_end"],
            "section_path": source["section_path"],
        },
    )
    assert added.status_code == 201, added.text
    assert client.delete(f"/projects/{projects[1]}", headers=headers).status_code == 204
    assert client.delete(path, headers=headers).status_code == 409
    assert db_session.get(KnowledgeNodeSource, added.json()["id"]) is not None
    assert (storage / version.storage_object_key).exists()

    # 自由 JSON 计划没有统一引用清单：保守保留曾绑定的资料。
    planned = upload(client, headers)
    project_id = projects[0]
    assert client.post(
        f"/projects/{project_id}/materials/{planned['material_id']}", headers=headers,
    ).status_code == 201
    assert client.delete(
        f"/projects/{project_id}/materials/{planned['material_id']}", headers=headers,
    ).status_code == 204
    user = db_session.scalar(select(User).where(User.username == "cleanup-history"))
    learning_plan_service.create_plan(
        db_session, project_id=project_id, user_id=user.id,
        payload=PlanCreate(content={}),
    )
    assert client.delete(f"/projects/{project_id}", headers=headers).status_code == 204
    rejected = client.delete(f"/materials/{planned['material_id']}", headers=headers)
    assert rejected.status_code == 409
    assert db_session.get(Material, planned["material_id"]).deletion_started_at is None


def test_queue_worker_and_late_queue_failure_cannot_race_cleanup(
    client, db_session, monkeypatch, storage,
):
    headers = login(client, "cleanup-jobs")
    item = upload(client, headers)
    version = db_session.get(Material, item["material_id"])
    parse_path = f"/materials/{item['material_id']}/parse"
    path = f"/materials/{item['material_id']}"
    monkeypatch.setattr(material_service.material_queue, "enqueue", lambda *args, **kwargs: None)
    queued = client.post(parse_path, headers=headers)
    assert queued.status_code == 202
    old_job = queued.json()["job_id"]
    assert client.delete(path, headers=headers).status_code == 409
    mark_material_parsing(db_session, version)
    restore_parse_queue_state(
        db_session, version, expected_job_id=old_job,
        parse_status="UPLOADED", parse_job_id=None, parser_name=None,
        parser_version=None, parse_error_code=None, parse_error_message=None,
        processed_at=None,
    )
    db_session.refresh(version)
    assert version.parse_status == "PARSING"
    assert client.delete(path, headers=headers).status_code == 409
    mark_material_failed(
        db_session, version, parser_name="test", parser_version="1",
        error_code="TEST_FAILURE", error_message="retry test",
    )
    retried = client.post(parse_path, headers=headers)
    assert retried.status_code == 202
    new_job = retried.json()["job_id"]
    monkeypatch.setattr(material_jobs, "SessionLocal", lambda: nullcontext(db_session))
    assert material_jobs.parse_material_job(version.id, old_job) == "ignored:stale_job"
    material_id = version.id
    assert material_jobs.parse_material_job(material_id, new_job) == "READY"
    assert client.delete(path, headers=headers).status_code == 204
    assert material_jobs.parse_material_job(material_id, new_job) == "ignored:not_found"
    assert not (storage / "parsed" / str(item["material_id"])).exists()


def test_partial_cleanup_stays_unusable_and_retry_finishes(
    client, db_session, monkeypatch, storage,
):
    headers = login(client, "cleanup-retry")
    item = upload(client, headers)
    version = parsed_version(db_session, item)
    project_id = project(client, headers)
    binding = f"/projects/{project_id}/materials/{item['material_id']}"
    assert client.post(binding, headers=headers).status_code == 201
    assert client.delete(binding, headers=headers).status_code == 204
    original = storage / version.storage_object_key
    parsed = storage / version.parsed_content_location
    sources = parsed.with_suffix(".sources.json")
    real_unlink = Path.unlink

    def fail_source_map(path, *args, **kwargs):
        if path == sources:
            raise PermissionError("simulated cleanup failure")
        return real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_source_map)
        response = client.delete(f"/materials/{item['material_id']}", headers=headers)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MATERIAL_DELETE_RETRY_REQUIRED"
    assert not original.exists() and sources.exists()
    assert db_session.get(Material, item["material_id"]).deletion_started_at is not None
    listed = client.get("/materials", headers=headers).json()["items"]
    assert listed[0]["deletion_pending"] is True
    assert client.post(binding, headers=headers).status_code == 404
    parse_path = f"/materials/{item['material_id']}/parse"
    assert client.post(parse_path, headers=headers).status_code == 404
    assert client.get(parse_path, headers=headers).status_code == 404
    user = db_session.scalar(select(User).where(User.username == "cleanup-retry"))
    with pytest.raises(HTTPException) as caught:
        learning_plan_service.create_plan(
            db_session, project_id=project_id, user_id=user.id,
            payload=PlanCreate(content={}),
        )
    assert caught.value.status_code == 409
    assert client.delete(f"/materials/{item['material_id']}", headers=headers).status_code == 204
    assert not parsed.exists() and not sources.exists()
    assert db_session.get(Material, item["material_id"]) is None
    assert list(db_session.scalars(select(ProjectMaterialBinding))) == []
    assert client.get("/materials", headers=headers).json()["items"] == []