from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repository import (
    create_user,
    get_user_by_id,
    get_user_by_username_or_email,
)
from app.schemas.user import UserCreate


def _user_exists_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "USER_ALREADY_EXISTS",
            "message": "username or email already exists",
        },
    )


def create_user_or_raise(db: Session, payload: UserCreate) -> User:
    email = str(payload.email)
    existing = get_user_by_username_or_email(
        db,
        username=payload.username,
        email=email,
    )
    if existing is not None:
        raise _user_exists_error()
    password_hash = hash_password(payload.password.get_secret_value())
    try:
        return create_user(
            db, username=payload.username, email=email, password_hash=password_hash
        )
    except IntegrityError:
        db.rollback()
        raise _user_exists_error() from None


def get_user_or_raise(db: Session, user_id: int) -> User:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": f"user {user_id} not found"},
        )
    return user
