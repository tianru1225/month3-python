def test_create_user_returns_201(client):
    response = client.post(
        "/users",
        json={"username":"bob","email":"bob@example.com"},
    )
    assert response.status_code ==201
    assert response.json()["username"] == "bob"
    assert response.json()["email"] == "bob@example.com"
def test_get_user_not_found_returns_404(client):
    response = client.get("/users/999999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "USER_NOT_FOUND"