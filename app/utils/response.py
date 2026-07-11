from typing import TypeVar
from app.schemas.response import ApiResponse

T = TypeVar("T")

def ok(data: T) -> ApiResponse[T]:
    return ApiResponse(data = data)
