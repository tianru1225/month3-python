from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    JWTConfigurationError,
    InvalidAccessTokenError,
    decode_access_token,
)
from app.deps.db import get_db
from app.models.user import User, UserStatus
from app.repositories.user_repository import get_user_by_id

_bearer_scheme = HTTPBearer(auto_error=False)


def verify_api_key(x_api_key: str | None = Header(default=None)) -> str:
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "API_KEY_MISSING", "message": "x-api-key header required"},
        )
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "API_KEY_INVALID", "message": "invalid api key"},
        )
    return x_api_key


def _bearer_error(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _bearer_error("AUTH_REQUIRED", "Bearer token required")
    try:
        user_id = decode_access_token(
            credentials.credentials,
            settings.jwt_secret_key.get_secret_value(),
        )
    except JWTConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "AUTH_CONFIGURATION_ERROR",
                "message": "authentication is not configured",
            },
        ) from exc
    except InvalidAccessTokenError as exc:
        raise _bearer_error("AUTH_INVALID", "invalid or expired bearer token") from exc

    user = get_user_by_id(db, user_id)
    if user is None:
        raise _bearer_error("AUTH_INVALID", "invalid or expired bearer token")
    if user.status != UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "USER_NOT_ACTIVE", "message": "user is not active"},
        )
    return user
