from sqlalchemy import func, select

from app.models.material import MaterialVersion, ParseStatus
from app.models.project_material import ProjectMaterialBinding


def _register_and_login(client, username: str) -> dict[str, str]:
    password = "day129-binding-password"
    register = client.post(
        "/users",
        json={"username": username, "password": password},
    )
    assert register.status_code == 201

    login = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_project(client, headers: dict[str, str], name: str) -> dict:
    response = client.post(
        "/projects",
        headers=headers,
        json={
            "name": name,
            "goal": "验证项目资料绑定",
            "current_level": "入门",
        },
    )
    assert response.status_code == 201
    return response.json()


def _upload_material(client, headers: dict[str, str], name: str) -> dict:
    response = client.post(
        "/materials",
        headers=headers,
        data={"name": name},
        files={
            "file": (
                f"{name}.md",
                f"# {name}\n\n正文".encode(),
                "text/markdown",
            )
        },
    )
    assert response.status_code == 201
    return response.json()


def _bind(client, headers: dict[str, str], project_id: int, material_id: int):
    return client.post(
        f"/projects/{project_id}/materials/{material_id}",
        headers=headers,
    )


def test_bind_is_idempotent_and_unbind_preserves_history(
    client,
    db_session,
) -> None:
    headers = _register_and_login(client, "binding-lifecycle")
    project = _create_project(client, headers, "绑定生命周期项目")
    material = _upload_material(client, headers, "lifecycle")
    path = f"/projects/{project['id']}/materials/{material['material_id']}"

    first = _bind(client, headers, project["id"], material["material_id"])
    duplicate = _bind(client, headers, project["id"], material["material_id"])

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]
    assert client.get(path.rsplit("/", 1)[0], headers=headers).json()

    assert client.delete(path, headers=headers).status_code == 204
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path.rsplit("/", 1)[0], headers=headers).json() == []

    history = list(db_session.scalars(select(ProjectMaterialBinding)))
    assert len(history) == 1
    assert history[0].unbound_at is not None

    rebound = _bind(client, headers, project["id"], material["material_id"])
    assert rebound.status_code == 201
    assert rebound.json()["id"] != first.json()["id"]
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ProjectMaterialBinding)
            .where(ProjectMaterialBinding.unbound_at.is_(None))
        )
        == 1
    )


def test_binding_requires_project_and_material_ownership(client) -> None:
    alice = _register_and_login(client, "binding-owner-alice")
    bob = _register_and_login(client, "binding-owner-bob")
    alice_project = _create_project(client, alice, "Alice 项目")
    bob_project = _create_project(client, bob, "Bob 项目")
    alice_material = _upload_material(client, alice, "alice-material")
    bob_material = _upload_material(client, bob, "bob-material")

    project_forbidden = _bind(
        client,
        bob,
        alice_project["id"],
        bob_material["material_id"],
    )
    assert project_forbidden.status_code == 404
    assert project_forbidden.json()["detail"]["code"] == "PROJECT_NOT_FOUND"

    material_forbidden = _bind(
        client,
        bob,
        bob_project["id"],
        alice_material["material_id"],
    )
    assert material_forbidden.status_code == 404
    assert material_forbidden.json()["detail"]["code"] == "MATERIAL_NOT_FOUND"

    missing_project = _bind(client, alice, 999999, bob_material["material_id"])
    missing_material = _bind(client, alice, alice_project["id"], 999999)
    assert missing_project.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert missing_material.json()["detail"]["code"] == "MATERIAL_NOT_FOUND"


def test_binding_routes_require_bearer(client) -> None:
    responses = [
        client.post("/projects/1/materials/1"),
        client.get("/projects/1/materials"),
        client.delete("/projects/1/materials/1"),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert [response.json()["detail"]["code"] for response in responses] == [
        "AUTH_REQUIRED",
        "AUTH_REQUIRED",
        "AUTH_REQUIRED",
    ]


def test_list_returns_only_active_bindings_in_bound_order(client) -> None:
    headers = _register_and_login(client, "binding-list-order")
    project = _create_project(client, headers, "列表项目")
    first = _upload_material(client, headers, "first")
    second = _upload_material(client, headers, "second")

    first_bind = _bind(client, headers, project["id"], first["material_id"])
    second_bind = _bind(client, headers, project["id"], second["material_id"])
    assert first_bind.status_code == 201
    assert second_bind.status_code == 201

    response = client.get(f"/projects/{project['id']}/materials", headers=headers)
    assert response.status_code == 200
    assert [item["material_id"] for item in response.json()] == [
        first["material_id"],
        second["material_id"],
    ]

    assert (
        client.delete(
            f"/projects/{project['id']}/materials/{first['material_id']}",
            headers=headers,
        ).status_code
        == 204
    )
    response = client.get(f"/projects/{project['id']}/materials", headers=headers)
    assert [item["material_id"] for item in response.json()] == [second["material_id"]]


def test_binding_uploaded_material_does_not_change_parse_status(
    client,
    db_session,
) -> None:
    headers = _register_and_login(client, "binding-uploaded-status")
    project = _create_project(client, headers, "状态项目")
    material = _upload_material(client, headers, "uploaded-status")

    response = _bind(client, headers, project["id"], material["material_id"])
    assert response.status_code == 201

    version = db_session.get(MaterialVersion, material["version_id"])
    assert version is not None
    assert version.parse_status == ParseStatus.UPLOADED.value


def test_other_user_cannot_list_or_unbind_project(client) -> None:
    owner = _register_and_login(client, "binding-private-owner")
    other = _register_and_login(client, "binding-private-other")
    project = _create_project(client, owner, "私有项目")
    material = _upload_material(client, owner, "private-material")
    assert (
        _bind(client, owner, project["id"], material["material_id"]).status_code == 201
    )

    list_response = client.get(
        f"/projects/{project['id']}/materials",
        headers=other,
    )
    delete_response = client.delete(
        f"/projects/{project['id']}/materials/{material['material_id']}",
        headers=other,
    )
    assert list_response.status_code == 404
    assert delete_response.status_code == 404
    assert list_response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert delete_response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
