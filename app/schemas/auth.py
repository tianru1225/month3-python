from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, StringConstraints

LoginIdentifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


class LoginRequest(BaseModel):
    identifier: LoginIdentifier
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_in: int
