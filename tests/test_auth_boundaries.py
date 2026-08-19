from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token
from app.models.user import User


def register_and_login(client, username: str) -> tuple[int, str]:
    created_response = client.post(
        "/users",
        json={
            "username": username,
            "password": "day119-password",
        },
    )
    assert created_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "username": username,
            "password": "day119-password",
        },
    )
    assert login_response.status_code == 200

    return created_response.json()["id"], login_response.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_current_user_and_own_user_route_work(client) -> None:
    user_id, token = register_and_login(client, "alice")

    me_response = client.get("/users/me", headers=bearer(token))
    own_response = client.get(f"/users/{user_id}", headers=bearer(token))

    assert me_response.status_code == 200
    assert own_response.status_code == 200
    assert me_response.json() == own_response.json()
    assert set(me_response.json()) == {"id", "username", "status", "created_at"}


def test_user_cannot_read_another_user(client) -> None:
    _, alice_token = register_and_login(client, "alice")
    bob_id, _ = register_and_login(client, "bob")

    response = client.get(f"/users/{bob_id}", headers=bearer(alice_token))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "USER_FORBIDDEN"


def test_signed_token_is_rejected_after_user_is_disabled(
    client,
    db_session,
) -> None:
    user_id, token = register_and_login(client, "alice")
    user = db_session.scalar(select(User).where(User.id == user_id))
    assert user is not None

    user.status = "DISABLED"
    db_session.commit()

    response = client.get("/users/me", headers=bearer(token))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "USER_NOT_ACTIVE"


def test_missing_expired_and_invalid_bearer_tokens_are_401(client) -> None:
    expired_token = create_access_token(
        1,
        settings.jwt_secret_key.get_secret_value(),
        timedelta(seconds=-1),
    )

    for headers in ({}, bearer("not-a-jwt"), bearer(expired_token)):
        response = client.get("/users/me", headers=headers)

        assert response.status_code == 401
        assert response.json()["detail"]["code"] in {
            "AUTH_REQUIRED",
            "AUTH_INVALID",
        }


def test_jwt_cannot_replace_api_key_and_api_key_cannot_replace_jwt(client) -> None:
    _, token = register_and_login(client, "alice")

    item_response = client.get("/items/1", headers=bearer(token))
    user_response = client.get(
        "/users/me",
        headers={"x-api-key": settings.api_key},
    )

    assert item_response.status_code == 401
    assert item_response.json()["detail"]["code"] == "API_KEY_MISSING"
    assert user_response.status_code == 401
    assert user_response.json()["detail"]["code"] == "AUTH_REQUIRED"
