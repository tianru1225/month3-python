import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.schemas.llm_stream import DoneEvent, ErrorEvent, StreamEvent
from app.schemas.chat import ChatMessage, ChatResult
from app.services.errors import LLMUpstreamError
from app.services.ollama_stream import parse_ollama_stream_line

logger = logging.getLogger("app.llm_stream")


class _OllamaChatResponse(BaseModel):
    model: str
    message: ChatMessage
    done_reason: str | None = None


def _build_ollama_payload(
    messages: list[ChatMessage], *, stream: bool
) -> dict[str, object]:
    return {
        "model": settings.ollama_model,
        "messages": [message.model_dump() for message in messages],
        "stream": stream,
        "options": {
            "num_ctx": settings.ollama_num_ctx,
            "num_predict": settings.ollama_num_predict,
        },
    }


def _build_ollama_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.ollama_connect_timeout_seconds,
        read=settings.ollama_read_timeout_seconds,
        write=30.0,
        pool=10.0,
    )


async def _chat_with_client(
    messages: list[ChatMessage], *, client: httpx.AsyncClient
) -> ChatResult:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    try:
        response = await client.post(
            url,
            json=_build_ollama_payload(messages, stream=False),
            timeout=_build_ollama_timeout(),
        )
        response.raise_for_status()
        upstream = _OllamaChatResponse.model_validate(response.json())
    except (
        httpx.HTTPError,
        json.JSONDecodeError,
        ValidationError,
    ) as exc:
        raise LLMUpstreamError("LLM upstream request failed") from exc

    return ChatResult(
        model=upstream.model,
        message=upstream.message,
        finish_reason=upstream.done_reason,
    )


async def chat_with_llm(
    messages: list[ChatMessage], *, client: httpx.AsyncClient | None = None
) -> ChatResult:
    if client is not None:
        return await _chat_with_client(messages, client=client)
    async with httpx.AsyncClient() as owned_client:
        return await _chat_with_client(messages, client=owned_client)


async def _stream_chat_with_client(
    messages: list[ChatMessage], *, client: httpx.AsyncClient
) -> AsyncGenerator[StreamEvent,None]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    try:
        async with client.stream(
            "POST",
            url,
            json=_build_ollama_payload(messages, stream=True),
            timeout=_build_ollama_timeout(),
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                events = parse_ollama_stream_line(line)

                for event in events:
                    yield event

                if any(isinstance(event, (DoneEvent, ErrorEvent)) for event in events):
                    return
    except asyncio.CancelledError:
        logger.info("LLM upstream stream cancelled")
        raise
    except httpx.HTTPError as exc:
        raise LLMUpstreamError("LLM 上游流式请求失败。") from exc


async def stream_chat_with_llm(
    messages: list[ChatMessage], *, client: httpx.AsyncClient | None = None
) -> AsyncGenerator[StreamEvent,None]:
    if client is not None:
        async for event in _stream_chat_with_client(messages, client=client):
            yield event
        return
    async with httpx.AsyncClient() as owned_client:
        async for event in _stream_chat_with_client(messages, client=owned_client):
            yield event
