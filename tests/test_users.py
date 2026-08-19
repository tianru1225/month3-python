import logging

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import verify_password
from app.models.user import User
from app.schemas.user import UserCreate


def test_register_user_hashes_password_and_returns_public_fields(
    client,
    db_session,
) -> None:
    password = "day118-secure-password"
    response = client.post(
        "/users",
        json={
            "username": "  bob  ",
            "password": password,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "username", "status", "created_at"}
    assert body["username"] == "bob"
    assert body["status"] == "ACTIVE"
    assert body["created_at"]
    assert "email" not in body
    assert "password" not in body
    assert "password_hash" not in body

    user = db_session.scalar(select(User).where(User.username == "bob"))
    assert user is not None
    assert user.password_hash != password
    assert verify_password(password, user.password_hash) is True


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "bob"},
        {
            "username": "bob",
            "password": "short",
        },
    ],
)
def test_register_user_rejects_missing_or_short_password(client, payload) -> None:
    response = client.post("/users", json=payload)
    assert response.status_code == 422


def test_user_create_redacts_password_from_representation() -> None:
    password = "day118-secret-password"
    payload = UserCreate(
        username="alice",
        password=password,
    )

    assert password not in repr(payload)
    assert password not in str(payload.model_dump())


def test_registration_does_not_log_password(client, caplog) -> None:
    password = "day118-not-in-logs"

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/users",
            json={
                "username": "log-check",
                "password": password,
            },
        )

    assert response.status_code == 201
    assert password not in caplog.text


def test_database_rejects_unknown_user_status(db_session) -> None:
    db_session.add(
        User(
            username="invalid-status",
            password_hash="test-password-hash",
            status="UNKNOWN",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_user_query_requires_bearer_token(client) -> None:
    response = client.get("/users/999999")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"
