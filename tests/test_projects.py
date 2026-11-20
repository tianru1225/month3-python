import pytest


def _register_and_login(client, username: str, password: str) -> dict[str, str]:
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
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()


def test_create_project_uses_current_user_and_defaults(client) -> None:
    headers = _register_and_login(
        client,
        "project-alice",
        "project-alice-password",
    )

    body = _create_project(client, headers, "  FastAPI 项目  ")

    assert set(body) == {"id", "name", "status", "created_at", "updated_at"}
    assert body["name"] == "FastAPI 项目"
    assert body["status"] == "ACTIVE"
    assert "user_id" not in body
    assert "password_hash" not in body

    detail = client.get(f"/projects/{body['id']}", headers=headers)
    listing = client.get("/projects", headers=headers)
    assert detail.status_code == 200
    assert listing.status_code == 200
    assert detail.json() == body
    assert listing.json() == [body]


def test_create_project_does_not_accept_owner_or_status(client) -> None:
    headers = _register_and_login(
        client,
        "project-owner-boundary",
        "project-owner-password",
    )
    response = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "所有权测试",
            "user_id": 999999,
            "status": "COMPLETED",
        },
    )

    assert response.status_code == 422
    assert {item["loc"][-1] for item in response.json()["detail"]} == {"user_id", "status"}
    assert client.get("/projects", headers=headers).json() == []


def test_list_projects_isolated_by_user(client) -> None:
    alice = _register_and_login(
        client,
        "project-list-alice",
        "project-list-alice-password",
    )
    bob = _register_and_login(
        client,
        "project-list-bob",
        "project-list-bob-password",
    )
    alice_project = _create_project(client, alice, "Alice 项目")
    bob_project = _create_project(client, bob, "Bob 项目")

    alice_list = client.get("/projects", headers=alice)
    bob_list = client.get("/projects", headers=bob)
    assert alice_list.status_code == 200
    assert bob_list.status_code == 200
    assert [item["id"] for item in alice_list.json()] == [alice_project["id"]]
    assert [item["id"] for item in bob_list.json()] == [bob_project["id"]]


def test_get_own_project(client) -> None:
    headers = _register_and_login(
        client,
        "project-detail-owner",
        "project-detail-password",
    )
    project = _create_project(client, headers, "详情项目")
    response = client.get(f"/projects/{project['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == project["id"]


def test_other_user_cannot_get_project(client) -> None:
    alice = _register_and_login(
        client,
        "project-access-alice",
        "project-access-alice-password",
    )
    bob = _register_and_login(
        client,
        "project-access-bob",
        "project-access-bob-password",
    )
    project = _create_project(client, alice, "Alice 私有项目")
    response = client.get(f"/projects/{project['id']}", headers=bob)

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "PROJECT_NOT_FOUND",
        "message": "project not found",
    }


def test_project_routes_require_bearer(client) -> None:
    responses = [
        client.post("/projects", json={"name": "未认证项目"}),
        client.get("/projects"),
        client.get("/projects/1"),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert [response.json()["detail"]["code"] for response in responses] == [
        "AUTH_REQUIRED",
        "AUTH_REQUIRED",
        "AUTH_REQUIRED",
    ]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "name"),
        ({"name": ""}, "name"),
        ({"name": " \t\n "}, "name"),
        ({"name": None}, "name"),
        ({"name": "x" * 121}, "name"),
    ],
)
def test_project_validation(client, payload: dict, field: str) -> None:
    headers = _register_and_login(
        client,
        "project-validation",
        "project-validation-password",
    )
    response = client.post("/projects", headers=headers, json=payload)

    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", field] for error in response.json()["detail"]
    )
    listing = client.get("/projects", headers=headers)
    assert listing.status_code == 200
    assert listing.json() == []


def test_project_accepts_maximum_name_length(client) -> None:
    headers = _register_and_login(client, "project-max-name", "project-max-name-password")
    body = _create_project(client, headers, "学" * 120)
    assert len(body["name"]) == 120


@pytest.mark.parametrize(
    "field",
    ["goal", "current_level", "deadline", "daily_minutes", "weekly_days", "expected_outcome"],
)
def test_project_rejects_retired_fields(client, field: str) -> None:
    headers = _register_and_login(client, "project-retired", "project-retired-password")
    response = client.post(
        "/projects", headers=headers, json={"name": "Name only", field: "legacy"},
    )
    assert response.status_code == 422
    assert any(
        item["loc"] == ["body", field] and item["type"] == "extra_forbidden"
        for item in response.json()["detail"]
    )
    assert client.get("/projects", headers=headers).json() == []


def test_project_list_empty_for_new_user(client) -> None:
    headers = _register_and_login(
        client,
        "project-empty-list",
        "project-empty-password",
    )
    response = client.get("/projects", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


def test_project_openapi_describes_name_only_request(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["ProjectCreate"]

    assert schema["required"] == ["name"]
    assert set(schema["properties"]) == {"name"}
    assert schema["additionalProperties"] is False