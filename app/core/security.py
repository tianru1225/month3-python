from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from jwt.exceptions import InvalidTokenError

_password_hasher = PasswordHasher()
_JWT_ALGORITHM = "HS256"
_MIN_JWT_SECRET_LENGTH = 32


class JWTConfigurationError(ValueError):
    pass


class InvalidAccessTokenError(ValueError):
    pass


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, ValueError):
        return False


def _validate_jwt_secret(secret_key: str) -> None:
    if len(secret_key) < _MIN_JWT_SECRET_LENGTH:
        raise JWTConfigurationError(
            "JWT_SECRET_KEY must contain at least 32 characters"
        )


def create_access_token(user_id: int, secret_key: str, expires_delta: timedelta) -> str:
    _validate_jwt_secret(secret_key)
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, secret_key, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> int:
    _validate_jwt_secret(secret_key)
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[_JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )

        subject = payload["sub"]
        if not isinstance(subject, str) or not subject.isdigit():
            raise InvalidAccessTokenError("invalid subject")
        user_id = int(subject)
        if user_id <= 0:
            raise InvalidAccessTokenError("invalid subject")
        return user_id
    except InvalidAccessTokenError:
        raise
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise InvalidAccessTokenError("invalid access token") from exc
