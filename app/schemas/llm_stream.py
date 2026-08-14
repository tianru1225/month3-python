from typing import Literal,TypeAlias

from pydantic import BaseModel,Field


class TextDeltaEvent(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str = Field(min_length=1)

class UsageEvent(BaseModel):
    type: Literal["usage"] = "usage"
    input_tokens: int | None = Field(default=None,ge=0)
    output_tokens: int | None = Field(default=None,ge=0)
    cached_input_tokens: int | None = Field(
        default=None,
        ge=0,
    )

class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    finish_reason: str | None = None

class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    retryable: bool = False

StreamEvent: TypeAlias = (
    TextDeltaEvent
    | UsageEvent
    | DoneEvent
    | ErrorEvent
)
