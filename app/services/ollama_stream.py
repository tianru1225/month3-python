import json
from collections.abc import Iterable, Iterator
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.schemas.llm_stream import (
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    TextDeltaEvent,
    UsageEvent,
)
from app.services.errors import LLMStreamProtocolError


class _OllamaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    content: str


class _OllamaStreamChunk(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    message: _OllamaMessage | None = None
    done: bool
    done_reason: str | None = None
    prompt_eval_count: int | None = Field(default=None, ge=0)
    eval_count: int | None = Field(default=None, ge=0)


def _decode_json_object(line: str | bytes) -> dict[str, object]:
    try:
        text = line.decode("utf-8") if isinstance(line, bytes) else line
        payload: object = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LLMStreamProtocolError(
            "Ollama 返回的流式数据不是合法的JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise LLMStreamProtocolError(
            "Ollama 返回的每一条流式数据，最外层必须是JSON 对象"
        )
    return cast(dict[str,object],payload)

def parse_ollama_stream_line(line: str | bytes) -> list[StreamEvent]:
    if not line.strip():
        return []
    payload = _decode_json_object(line)
    if "error" in payload:
        message = payload["error"]
        if not isinstance(message,str) or not message.strip():
            raise LLMStreamProtocolError(
                "Ollama 返回的错误事件中，必须有实际内容的错误信息"
            )
        return [ErrorEvent(code="OLLAMA_STREAM_ERROR",message = message.strip(),retryable=False)]
    try:
        chunk = _OllamaStreamChunk.model_validate(payload)
    except ValidationError as exc:
        raise LLMStreamProtocolError(
            "Ollama 返回的流式数据结构不符合预期"
        ) from exc
    if not chunk.done and chunk.message is None:
        raise LLMStreamProtocolError(
            "Ollama 返回的是一条文本事件，但其中没有消息内容。"
        )
    events: list[StreamEvent] = []
    if chunk.message is not None and chunk.message.content:
        events.append(TextDeltaEvent(text = chunk.message.content))
    if not chunk.done:
        return events
    if chunk.prompt_eval_count is not None or chunk.eval_count is not None:
        events.append(
            UsageEvent(input_tokens=chunk.prompt_eval_count,output_tokens=chunk.eval_count)
        )
    events.append(
        DoneEvent(finish_reason=chunk.done_reason)
    )
    return events
def parse_ollama_stream(lines: Iterable[str | bytes]) -> Iterator[StreamEvent]:
    for line in lines:
        events = parse_ollama_stream_line(line)
        for event in events:
            yield event
        if any(isinstance(event,(DoneEvent,ErrorEvent)) for event in events):
            return