def test_get_item_without_api_key_returns_401(client):
    response = client.get("/items/1")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "API_KEY_MISSING"


def test_get_item_with_wrong_api_key_returns_401(client):
    response = client.get("/items/1", headers={"x-api-key": "wrong-key"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "API_KEY_INVALID"


def test_get_item_with_valid_api_key_returns_200(client):
    response = client.get("/items/1", headers={"x-api-key": "day69-new-key"})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["msg"] == "success"
    assert body["data"] == {"item_id": 1, "name": "demo-item"}


def test_create_item_invalid_body_returns_422(client):
    response = client.post(
        "/items",
        headers={"x-api-key": "day69-new-key"},
        json={"name": "apple", "price": "abc"},
    )
    assert response.status_code == 422