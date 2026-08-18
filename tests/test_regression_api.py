def test_debug_request_id_auto_generated_matches_response_header(client):
    response = client.get("/debug/request-id")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["msg"] == "success"
    assert body["data"]["request_id"]
    assert response.headers["x-request-id"] == body["data"]["request_id"]


def test_boom_returns_teapot_error_contract(client):
    response = client.get("/boom")
    body = response.json()

    assert body["detail"]["code"] == "TEAPOT"
    assert body["detail"]["message"] == "day66 teapot"


def test_boom_error_response_has_request_id_header(client):
    response = client.get(
        "/boom",
        headers={"X-Request-ID": "day088-boom"},
    )
    assert response.status_code == 418
    assert response.headers["x-request-id"] == "day088-boom"


def test_item_not_found_keeps_error_contract(client):
    response = client.get(
        "/items/999",
        headers={"x-api-key": "day69-new-key"},
    )
    assert response.status_code == 404

    body = response.json()

    assert body["detail"]["code"] == "ITEM_NOT_FOUND"
    assert body["detail"]["message"] == "item 999 not found"


def test_create_item_success_keeps_unified_response_contract(client):
    response = client.post(
        "/items",
        headers={"x-api-key": "day69-new-key"},
        json={"name": "day088-item", "price": 88.0},
    )
    assert response.status_code == 200

    body = response.json()

    assert body["code"] == "OK"
    assert body["msg"] == "success"
    assert body["data"]["name"] == "day088-item"
    assert body["data"]["price"] == 88.0
    assert body["data"]["message"] == "day70 ok"


def test_create_user_then_get_user_roundtrip(client):
    create_response = client.post(
        "/users",
        json={
            "username": "day088-user",
            "email": "day088@example.com",
            "password": "day118-regression-password",
        },
    )
    assert create_response.status_code == 201
    created_user = create_response.json()

    login_response = client.post(
        "/auth/login",
        json={
            "identifier": "day088-user",
            "password": "day118-regression-password",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    get_response = client.get(
        f"/users/{created_user['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_response.status_code == 200
    fetched_user = get_response.json()

    assert fetched_user["id"] == created_user["id"]
    assert fetched_user["username"] == "day088-user"
    assert fetched_user["email"] == "day088@example.com"
    assert fetched_user["status"] == "ACTIVE"
    assert fetched_user["created_at"]
    assert "password" not in fetched_user
    assert "password_hash" not in fetched_user


def test_create_user_duplicate_username_returns_error_contract(client):
    first_response = client.post(
        "/users",
        json={
            "username": "day088-dup",
            "email": "day088-dup-1@example.com",
            "password": "day118-regression-password",
        },
    )
    assert first_response.status_code == 201

    duplicate_response = client.post(
        "/users",
        json={
            "username": "day088-dup",
            "email": "day088-dup-2@example.com",
            "password": "day118-regression-password",
        },
    )
    assert duplicate_response.status_code == 400
    body = duplicate_response.json()

    assert body["detail"]["code"] == "USER_ALREADY_EXISTS"


def test_create_user_duplicate_email_returns_error_contract(client):
    first_response = client.post(
        "/users",
        json={
            "username": "day088-email-1",
            "email": "day088-email@example.com",
            "password": "day118-regression-password",
        },
    )
    assert first_response.status_code == 201

    duplicate_response = client.post(
        "/users",
        json={
            "username": "day088-email-2",
            "email": "day088-email@example.com",
            "password": "day118-regression-password",
        },
    )

    assert duplicate_response.status_code == 400
    body = duplicate_response.json()

    assert body["detail"]["code"] == "USER_ALREADY_EXISTS"


def test_openapi_contains_core_paths(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/debug/request-id" in paths
    assert "/boom" in paths
    assert "/items" in paths
    assert "/items/{item_id}" in paths
    assert "/users" in paths
    assert "/users/me" in paths
    assert "/users/{user_id}" in paths
    assert "/auth/login" in paths
    assert "/tasks/audit" in paths


def test_openapi_core_paths_have_expected_methods(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "get" in paths["/health"]
    assert "get" in paths["/debug/request-id"]
    assert "get" in paths["/boom"]
    assert "post" in paths["/items"]
    assert "get" in paths["/items/{item_id}"]
    assert "post" in paths["/users"]
    assert "post" in paths["/auth/login"]
    assert "get" in paths["/users/me"]
    assert "get" in paths["/users/{user_id}"]
    assert "post" in paths["/tasks/audit"]
