from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    JWTConfigurationError,
    create_access_token,
    verify_password,
)
from app.models.user import UserStatus
from app.repositories.user_repository import get_user_by_identifier
from app.schemas.auth import LoginRequest, TokenResponse


def _invalid_credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "INVALID_CREDENTIALS",
            "message": "invalid credentials",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def login_user_or_raise(db: Session, payload: LoginRequest) -> TokenResponse:
    user = get_user_by_identifier(db, payload.identifier)
    password = payload.password.get_secret_value()
    password_hash = user.password_hash if user is not None else "!unknown-user"

    if user is None or not verify_password(password, password_hash):
        raise _invalid_credentials_error()
    if user.status != UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "USER_NOT_ACTIVE", "message": "user is not active"},
        )

    try:
        access_token = create_access_token(
            user.id,
            settings.jwt_secret_key.get_secret_value(),
            timedelta(minutes=settings.jwt_access_token_expire_minutes),
        )
    except JWTConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "AUTH_CONFIGURATION_ERROR",
                "message": "authentication is not configured",
            },
        ) from exc
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )
