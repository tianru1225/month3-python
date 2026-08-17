import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.schemas.user import UserCreate
from app.services import user_service
from app.services.user_service import create_user_or_raise, get_user_or_raise


def user_payload(
    *,
    username: str,
    email: str,
) -> UserCreate:
    return UserCreate(
        username=username,
        email=email,
        password="day118-valid-password",
    )


def test_create_user_or_raise_rejects_duplicate_username(db_session) -> None:
    create_user_or_raise(
        db_session,
        user_payload(username="alice", email="alice@example.com"),
    )

    with pytest.raises(HTTPException) as exc_info:
        create_user_or_raise(
            db_session,
            user_payload(username="alice", email="alice2@example.com"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "USER_ALREADY_EXISTS"


def test_create_user_or_raise_rejects_duplicate_email(db_session) -> None:
    create_user_or_raise(
        db_session,
        user_payload(username="alice", email="alice@example.com"),
    )

    with pytest.raises(HTTPException) as exc_info:
        create_user_or_raise(
            db_session,
            user_payload(username="bob", email="alice@example.com"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "USER_ALREADY_EXISTS"


def test_create_user_or_raise_handles_unique_constraint_race(monkeypatch) -> None:
    class FakeSession:
        rolled_back = False

        def rollback(self) -> None:
            self.rolled_back = True

    db = FakeSession()

    monkeypatch.setattr(
        user_service,
        "get_user_by_username_or_email",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        user_service,
        "hash_password",
        lambda _password: "password-hash",
    )

    def raise_integrity_error(*_args, **_kwargs):
        raise IntegrityError("INSERT", {}, Exception("unique violation"))

    monkeypatch.setattr(user_service, "create_user", raise_integrity_error)

    with pytest.raises(HTTPException) as exc_info:
        create_user_or_raise(
            db,  # type: ignore[arg-type]
            user_payload(username="alice", email="alice@example.com"),
        )

    assert db.rolled_back is True
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "USER_ALREADY_EXISTS"


def test_get_user_or_raise_rejects_missing_user(db_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_user_or_raise(db_session, 999999)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "USER_NOT_FOUND"
