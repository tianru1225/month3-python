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
        json={
            "name": name,
            "goal": "完成一个可验证的 FastAPI 后端项目",
            "current_level": "已有 Python 基础",
            "deadline": "2026-10-31",
            "daily_minutes": 60,
            "weekly_days": 5,
            "expected_outcome": "能够独立实现并测试 API",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_project_uses_current_user_and_defaults(client) -> None:
    headers = _register_and_login(
        client,
        "project-alice",
        "project-alice-password",
    )

    response = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "  FastAPI 项目  ",
            "goal": "完成后端 API",
            "current_level": "入门",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "FastAPI 项目"
    assert body["daily_minutes"] == 60
    assert body["weekly_days"] == 7
    assert body["status"] == "ACTIVE"
    assert body["deadline"] is None
    assert body["expected_outcome"] is None
    assert "user_id" not in body
    assert "password_hash" not in body


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
            "user_id": 999999,
            "status": "COMPLETED",
            "name": "所有权测试",
            "goal": "验证服务端决定所有者和初始状态",
            "current_level": "入门",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "ACTIVE"
    assert "user_id" not in response.json()


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
    _create_project(client, bob, "Bob 项目")

    response = client.get("/projects", headers=alice)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [alice_project["id"]]
    assert [item["name"] for item in response.json()] == ["Alice 项目"]


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
    payload = {
        "name": "未认证项目",
        "goal": "不应创建",
        "current_level": "入门",
    }

    responses = [
        client.post("/projects", json=payload),
        client.get("/projects"),
        client.get("/projects/1"),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert [response.json()["detail"]["code"] for response in responses] == [
        "AUTH_REQUIRED",
        "AUTH_REQUIRED",
        "AUTH_REQUIRED",
    ]


def test_project_validation(client) -> None:
    headers = _register_and_login(
        client,
        "project-validation",
        "project-validation-password",
    )

    missing = client.post(
        "/projects",
        headers=headers,
        json={"name": "缺字段项目"},
    )
    invalid_range = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "范围项目",
            "goal": "测试时间范围",
            "current_level": "入门",
            "daily_minutes": 0,
            "weekly_days": 8,
        },
    )

    assert missing.status_code == 422
    assert invalid_range.status_code == 422


def test_project_list_empty_for_new_user(client) -> None:
    headers = _register_and_login(
        client,
        "project-empty-list",
        "project-empty-password",
    )

    response = client.get("/projects", headers=headers)

    assert response.status_code == 200
    assert response.json() == []
