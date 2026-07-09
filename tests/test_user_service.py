import pytest
from fastapi import HTTPException

from app.schemas.user import UserCreate
from app.services.user_service import create_user_or_raise,get_user_or_raise

def test_create_user_or_raise_rejects_duplicate_username(db_session):
    create_user_or_raise(
        db_session,
        UserCreate(username="alice",email="alice@example.com"),
    )
    with pytest.raises(HTTPException) as exc_info:
        create_user_or_raise(
            db_session,
            UserCreate(username = "alice",email = "alice2@example.com"),
        )
    
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] =="USER_ALREADY_EXISTS"

def test_create_user_or_raise_rejects_duplicate_email(db_session):
    create_user_or_raise(
        db_session,
        UserCreate(username="alice", email="alice@example.com"),
    )
    with pytest.raises(HTTPException) as exc_info:
        create_user_or_raise(
            db_session,
            UserCreate(username="bob", email="alice@example.com"),
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "USER_ALREADY_EXISTS"

def test_get_user_or_raise_rejects_missing_user(db_session):
    with pytest.raises(HTTPException) as exc_info:
        get_user_or_raise(db_session, 999999)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "USER_NOT_FOUND"