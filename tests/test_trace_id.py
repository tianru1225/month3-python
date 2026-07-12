def test_response_has_x_request_id(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"]

def test_response_reuses_incoming_x_request_id(client):
    response = client.get(
        "/health",
        headers = {"X-Request-ID":"test-request-id"}
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-request-id"

def test_debug_request_id_returns_current_request_id(client):
    response = client.get(
        "/debug/request-id",
        headers = {"X-Request-ID": "debug-request-id"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["data"]["request_id"] == "debug-request-id"