from datetime import timedelta

import jwt
import pytest

from app.config import Settings
from app.core.security import (
    InvalidAccessTokenError,
    JWTConfigurationError,
    create_access_token,
    decode_access_token,
)

SECRET = "day119-test-jwt-secret-32-chars-long"


def test_access_token_claims_and_decode():
    token = create_access_token(7, SECRET, timedelta(minutes=30))
    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert payload["sub"] == "7"
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert decode_access_token(token, SECRET) == 7


@pytest.mark.parametrize(
    "token_factory",
    [
        lambda: create_access_token(7, SECRET, timedelta(seconds=-1)),
        lambda: create_access_token(7, SECRET, timedelta(minutes=30))[:-1] + "x",
        lambda: jwt.encode(
            {"sub": "7", "iat": 1, "exp": 9999999999},
            "wrong-secret",
            algorithm="HS256",
        ),
        lambda: jwt.encode({"sub": "7", "iat": 1}, SECRET, algorithm="HS256"),
        lambda: jwt.encode(
            {"sub": "abc", "iat": 1, "exp": 9999999999},
            SECRET,
            algorithm="HS256",
        ),
    ],
)
def test_invalid_access_tokens_are_rejected(token_factory):
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token_factory(), SECRET)


def test_short_secret_is_rejected():
    with pytest.raises(JWTConfigurationError):
        create_access_token(1, "short", timedelta(minutes=30))


def test_jwt_configuration_is_redacted():
    configured = Settings(_env_file=None, jwt_secret_key=SECRET)
    assert SECRET not in repr(configured)
    assert SECRET not in str(configured.model_dump())
