import logging

from sqlalchemy import select

from app.models.user import User


def register(client, username: str, email: str, password: str = "day119-password"):
    return client.post(
        "/users",
        json={"username": username, "email": email, "password": password},
    )


def login(client, identifier: str, password: str = "day119-password"):
    return client.post(
        "/auth/login",
        json={"identifier": identifier, "password": password},
    )


def test_login_by_username_and_email_returns_bearer_token(client) -> None:
    assert register(client, "alice", "alice@example.com").status_code == 201

    username_response = login(client, "alice")
    email_response = login(client, "alice@example.com")

    assert username_response.status_code == 200
    assert email_response.status_code == 200

    for response in (username_response, email_response):
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["expires_in"] == 1800


def test_unknown_user_and_wrong_password_have_same_401_contract(client) -> None:
    assert register(client, "alice", "alice@example.com").status_code == 201

    unknown_response = login(client, "nobody@example.com")
    wrong_password_response = login(client, "alice", "wrong-password")

    assert unknown_response.status_code == 401
    assert wrong_password_response.status_code == 401
    assert unknown_response.json()["detail"] == wrong_password_response.json()["detail"]
    assert unknown_response.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert unknown_response.headers["www-authenticate"] == "Bearer"


def test_disabled_and_locked_users_cannot_login(client, db_session) -> None:
    assert register(client, "disabled", "disabled@example.com").status_code == 201
    assert register(client, "locked", "locked@example.com").status_code == 201

    disabled = db_session.scalar(select(User).where(User.username == "disabled"))
    locked = db_session.scalar(select(User).where(User.username == "locked"))
    assert disabled is not None
    assert locked is not None

    disabled.status = "DISABLED"
    locked.status = "LOCKED"
    db_session.commit()

    disabled_response = login(client, "disabled")
    locked_response = login(client, "locked")

    assert disabled_response.status_code == 403
    assert locked_response.status_code == 403
    assert disabled_response.json()["detail"]["code"] == "USER_NOT_ACTIVE"
    assert locked_response.json()["detail"]["code"] == "USER_NOT_ACTIVE"


def test_login_does_not_log_password_or_token(client, caplog) -> None:
    password = "day119-password-not-in-logs"

    with caplog.at_level(logging.INFO):
        assert (
            register(
                client,
                "loguser",
                "loguser@example.com",
                password,
            ).status_code
            == 201
        )
        response = login(client, "loguser", password)

    assert response.status_code == 200
    assert password not in caplog.text
    assert response.json()["access_token"] not in caplog.text
