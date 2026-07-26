from typing import Literal

from pydantic import BaseModel,Field


class ChatMessage(BaseModel):
    role: Literal["system","user","assistant"]
    content: str = Field(min_length=1,max_length=8000)
class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1,max_length=32)
class ChatResult(BaseModel):
    model: str
    message: ChatMessage
    finish_reason: str | None = None

