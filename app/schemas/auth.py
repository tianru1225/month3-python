from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from app.schemas.user import Username


class LoginRequest(BaseModel):
    username: Username
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_in: int
