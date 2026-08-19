from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
)

from app.models.user import UserStatus

Username = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=3, max_length=50)
]


class UserCreate(BaseModel):
    username: Username
    password: SecretStr = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    status: UserStatus
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
