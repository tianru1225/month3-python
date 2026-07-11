def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["msg"] == "success"
    assert body["data"]["status"] == "ok"