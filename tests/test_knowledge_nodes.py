import json

import pytest
from sqlalchemy import select

from app.models.learning_project import LearningProject
from app.models.material import Material, MaterialVersion, ParseStatus
from app.models.project_material import ProjectMaterialBinding
from app.services import knowledge_service


@pytest.fixture(autouse=True)
def isolated_material_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        knowledge_service,
        "MATERIAL_STORAGE_DIR",
        tmp_path / "materials",
    )


def _register_and_login(client, username: str) -> dict[str, str]:
    password = "day132-knowledge-password"
    assert (
        client.post(
            "/users",
            json={"username": username, "password": password},
        ).status_code
        == 201
    )
    response = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(db_session, username: str) -> int:
    from app.models.user import User

    user = db_session.scalar(select(User).where(User.username == username))
    assert user is not None
    return user.id


def _project(db_session, user_id: int, name: str) -> LearningProject:
    project = LearningProject(
        user_id=user_id,
        name=name,
        goal="建立项目知识点图",
        current_level="beginner",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _node(client, headers, project_id: int, title: str) -> dict:
    response = client.post(
        f"/projects/{project_id}/knowledge-nodes",
        headers=headers,
        json={
            "title": title,
            "description": f"{title} description",
            "difficulty": 3,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_list_get_and_owner_scope(client, db_session) -> None:
    headers = _register_and_login(client, "knowledge-owner")
    other = _register_and_login(client, "knowledge-other")
    project = _project(db_session, _user_id(db_session, "knowledge-owner"), "owner")
    node = _node(client, headers, project.id, "Markdown basics")

    listed = client.get(
        f"/projects/{project.id}/knowledge-nodes",
        headers=headers,
    )
    detail = client.get(
        f"/projects/{project.id}/knowledge-nodes/{node['id']}",
        headers=headers,
    )
    forbidden = client.get(
        f"/projects/{project.id}/knowledge-nodes",
        headers=other,
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [node["id"]]
    assert detail.status_code == 200
    assert detail.json()["status"] == "DRAFT"
    assert detail.json()["sources"] == []
    assert forbidden.status_code == 404
    assert forbidden.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    [
        {"title": " ", "description": "valid"},
        {"title": "valid", "description": " "},
        {"title": "valid", "description": "valid", "difficulty": 0},
        {"title": "valid", "description": "valid", "difficulty": 6},
    ],
)
def test_node_validation(client, db_session, payload) -> None:
    headers = _register_and_login(client, "knowledge-validation")
    project = _project(
        db_session,
        _user_id(db_session, "knowledge-validation"),
        "validation",
    )
    response = client.post(
        f"/projects/{project.id}/knowledge-nodes",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 422


def test_prerequisite_idempotency_cycle_and_delete(client, db_session) -> None:
    headers = _register_and_login(client, "knowledge-graph")
    project = _project(db_session, _user_id(db_session, "knowledge-graph"), "graph")
    foundation = _node(client, headers, project.id, "Foundation")
    advanced = _node(client, headers, project.id, "Advanced")

    path = (
        f"/projects/{project.id}/knowledge-nodes/{advanced['id']}"
        f"/prerequisites/{foundation['id']}"
    )
    reverse = (
        f"/projects/{project.id}/knowledge-nodes/{foundation['id']}"
        f"/prerequisites/{advanced['id']}"
    )

    first = client.post(path, headers=headers)
    duplicate = client.post(path, headers=headers)
    cycle = client.post(reverse, headers=headers)
    deleted = client.delete(path, headers=headers)
    repeated_delete = client.delete(path, headers=headers)

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]
    assert cycle.status_code == 409
    assert cycle.json()["detail"]["code"] == "KNOWLEDGE_PREREQUISITE_CYCLE"
    assert deleted.status_code == 204
    assert repeated_delete.status_code == 204


def test_self_and_cross_project_edges_are_rejected(client, db_session) -> None:
    headers = _register_and_login(client, "knowledge-cross-project")
    user_id = _user_id(db_session, "knowledge-cross-project")
    project = _project(db_session, user_id, "one")
    other_project = _project(db_session, user_id, "two")
    node = _node(client, headers, project.id, "One")
    foreign = _node(client, headers, other_project.id, "Foreign")

    self_path = (
        f"/projects/{project.id}/knowledge-nodes/{node['id']}"
        f"/prerequisites/{node['id']}"
    )
    foreign_path = (
        f"/projects/{project.id}/knowledge-nodes/{node['id']}"
        f"/prerequisites/{foreign['id']}"
    )

    self_response = client.post(self_path, headers=headers)
    foreign_response = client.post(foreign_path, headers=headers)

    assert self_response.status_code == 400
    assert self_response.json()["detail"]["code"] == "KNOWLEDGE_PREREQUISITE_INVALID"
    assert foreign_response.status_code == 404
    assert foreign_response.json()["detail"]["code"] == "KNOWLEDGE_NODE_NOT_FOUND"


def _ready_source(db_session, project_id: int, user_id: int, tmp_path):
    material = Material(user_id=user_id, name="source")
    db_session.add(material)
    db_session.flush()
    version = MaterialVersion(
        material_id=material.id,
        version_number=1,
        original_filename="guide.md",
        normalized_format="markdown",
        mime_type="text/markdown",
        size_bytes=30,
        content_hash="d" * 64,
        storage_object_key=f"{user_id}/guide.md",
        parser_name="markdown-token-parser",
        parser_version="markdown-it-py-3.0.0",
        parse_status=ParseStatus.READY.value,
        source_metadata={
            "kind": "markdown",
            "line_count": 3,
            "sources_path": "parsed/PENDING.sources.json",
        },
    )
    db_session.add(version)
    db_session.flush()
    version.source_metadata = {
        "kind": "markdown",
        "line_count": 3,
        "sources_path": f"parsed/{material.id}/{version.id}.sources.json",
    }
    db_session.add(
        ProjectMaterialBinding(project_id=project_id, material_id=material.id)
    )
    db_session.commit()

    source_path = (
        tmp_path
        / "materials"
        / "parsed"
        / str(material.id)
        / f"{version.id}.sources.json"
    )
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        json.dumps(
            {
                "material_version_id": version.id,
                "blocks": [
                    {
                        "text": "# Foundations\n\nMarkdown graph\n",
                        "source": {
                            "line_start": 1,
                            "line_end": 3,
                            "section_path": ["Foundations"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return version


def test_source_requires_real_ready_binding_and_location(
    client, db_session, tmp_path
) -> None:
    headers = _register_and_login(client, "knowledge-source")
    user_id = _user_id(db_session, "knowledge-source")
    project = _project(db_session, user_id, "sources")
    node = _node(client, headers, project.id, "Source node")
    version = _ready_source(db_session, project.id, user_id, tmp_path)

    response = client.post(
        f"/projects/{project.id}/knowledge-nodes/{node['id']}/sources",
        headers=headers,
        json={
            "material_version_id": version.id,
            "block_index": 0,
            "line_start": 1,
            "line_end": 3,
            "section_path": ["Foundations"],
            "quote": "Markdown graph",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["material_version_id"] == version.id
    assert response.json()["quote_hash"]


def test_source_rejects_fake_location_and_unbound_version(
    client, db_session, tmp_path
) -> None:
    headers = _register_and_login(client, "knowledge-source-invalid")
    user_id = _user_id(db_session, "knowledge-source-invalid")
    project = _project(db_session, user_id, "invalid-source")
    node = _node(client, headers, project.id, "Source node")
    version = _ready_source(db_session, project.id, user_id, tmp_path)
    db_session.query(ProjectMaterialBinding).filter(
        ProjectMaterialBinding.material_id == version.material_id
    ).delete()
    db_session.commit()

    response = client.post(
        f"/projects/{project.id}/knowledge-nodes/{node['id']}/sources",
        headers=headers,
        json={
            "material_version_id": version.id,
            "block_index": 0,
            "line_start": 999,
            "line_end": 999,
            "section_path": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "KNOWLEDGE_SOURCE_INVALID"


def test_knowledge_routes_require_bearer(client) -> None:
    response = client.get("/projects/1/knowledge-nodes")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"
