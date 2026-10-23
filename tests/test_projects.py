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

    assert body["name"] == "FastAPI 项目"
    assert body["goal"] == "从上传资料开始完成系统学习"
    assert body["current_level"] == "beginner"
    assert body["daily_minutes"] == 60
    assert body["weekly_days"] == 7
    assert body["status"] == "ACTIVE"
    assert body["deadline"] is None
    assert body["expected_outcome"] is None
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

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert "user_id" not in body
    listing = client.get("/projects", headers=headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [body["id"]]


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
        ({"name": "校验项目", "goal": ""}, "goal"),
        ({"name": "校验项目", "goal": "   "}, "goal"),
        ({"name": "校验项目", "goal": None}, "goal"),
        ({"name": "校验项目", "current_level": ""}, "current_level"),
        ({"name": "校验项目", "current_level": "   "}, "current_level"),
        ({"name": "校验项目", "current_level": None}, "current_level"),
        ({"name": "校验项目", "daily_minutes": 0}, "daily_minutes"),
        ({"name": "校验项目", "daily_minutes": 1441}, "daily_minutes"),
        ({"name": "校验项目", "daily_minutes": None}, "daily_minutes"),
        ({"name": "校验项目", "weekly_days": 0}, "weekly_days"),
        ({"name": "校验项目", "weekly_days": 8}, "weekly_days"),
        ({"name": "校验项目", "weekly_days": None}, "weekly_days"),
        ({"name": "校验项目", "expected_outcome": "   "}, "expected_outcome"),
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


@pytest.mark.parametrize(
    ("daily_minutes", "weekly_days"),
    [(1, 1), (1440, 7)],
)
def test_project_accepts_valid_boundaries(
    client, daily_minutes: int, weekly_days: int
) -> None:
    headers = _register_and_login(
        client,
        "project-valid-bounds",
        "project-valid-bounds-password",
    )
    response = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "学" * 120,
            "daily_minutes": daily_minutes,
            "weekly_days": weekly_days,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["name"]) == 120
    assert body["daily_minutes"] == daily_minutes
    assert body["weekly_days"] == weekly_days


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
    properties = schema["properties"]
    assert properties["goal"]["default"] == "从上传资料开始完成系统学习"
    assert properties["current_level"]["default"] == "beginner"
    assert properties["daily_minutes"]["default"] == 60
    assert properties["daily_minutes"]["minimum"] == 1
    assert properties["weekly_days"]["default"] == 7