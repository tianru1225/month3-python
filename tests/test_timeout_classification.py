import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from app.config import settings
from app.schemas.chat import ChatMessage
from app.schemas.llm_stream import (
    StreamEvent,
    TextDeltaEvent,
)
from app.services.errors import (
    LLMGenerationTimeoutError,
    LLMUpstreamConnectionError,
)
from app.services.llm_service import (
    chat_with_llm,
    stream_chat_with_llm,
)


def _messages() -> list[ChatMessage]:
    return [
        ChatMessage(
            role="user",
            content="hello",
        )
    ]


def _payload() -> dict[str, list[dict[str, str]]]:
    return {
        "messages": [
            {
                "role": "user",
                "content": "hello",
            }
        ]
    }


def test_connect_timeout_is_classified_and_uses_full_budget() -> None:
    captured_timeout: dict[str, float] = {}

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        captured_timeout.update(request.extensions["timeout"])
        raise httpx.ConnectTimeout(
            "connection timed out",
            request=request,
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as injected:
            await chat_with_llm(
                _messages(),
                client=injected,
            )

    with pytest.raises(LLMUpstreamConnectionError) as exc_info:
        asyncio.run(run())

    assert isinstance(
        exc_info.value.__cause__,
        httpx.ConnectTimeout,
    )

    error = exc_info.value
    assert (
        error.code,
        error.public_message,
        error.http_status,
        error.retryable,
    ) == (
        "LLM_UPSTREAM_CONNECTION_ERROR",
        "LLM upstream is unavailable",
        503,
        True,
    )

    assert captured_timeout == {
        "connect": (settings.ollama_connect_timeout_seconds),
        "read": (settings.ollama_read_timeout_seconds),
        "write": (settings.ollama_write_timeout_seconds),
        "pool": (settings.ollama_pool_timeout_seconds),
    }


class TimeoutAfterFirstLine(httpx.AsyncByteStream):
    def __init__(
        self,
        request: httpx.Request,
    ) -> None:
        self.request = request
        self.closed = False

    async def __aiter__(
        self,
    ) -> AsyncIterator[bytes]:
        yield (b'{"message":{"content":"first"},"done":false}\n')
        raise httpx.ReadTimeout(
            "upstream stopped producing data",
            request=self.request,
        )

    async def aclose(self) -> None:
        self.closed = True


def test_stream_read_timeout_is_classified_and_closes_response() -> None:
    body_holder: dict[
        str,
        TimeoutAfterFirstLine,
    ] = {}

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        body = TimeoutAfterFirstLine(request)
        body_holder["body"] = body

        return httpx.Response(
            200,
            headers={"content-type": ("application/x-ndjson")},
            stream=body,
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as injected:
            stream = stream_chat_with_llm(
                _messages(),
                client=injected,
            )

            first = await anext(stream)
            assert first == TextDeltaEvent(text="first")

            with pytest.raises(LLMGenerationTimeoutError) as exc_info:
                await anext(stream)

            assert isinstance(
                exc_info.value.__cause__,
                httpx.ReadTimeout,
            )

    asyncio.run(run())

    assert body_holder["body"].closed


def test_non_stream_timeout_returns_504(
    client,
    monkeypatch,
) -> None:
    async def fake_chat(
        messages: list[ChatMessage],
    ):
        assert messages
        raise LLMGenerationTimeoutError("read timed out")

    monkeypatch.setattr(
        "app.routers.chat.chat_with_llm",
        fake_chat,
    )

    response = client.post(
        "/v1/chat",
        headers={"x-api-key": settings.api_key},
        json=_payload(),
    )

    assert response.status_code == 504
    assert response.json()["detail"] == {
        "code": "LLM_GENERATION_TIMEOUT",
        "message": "LLM generation timed out",
    }


def test_stream_timeout_returns_terminal_error_event(
    client,
    monkeypatch,
) -> None:
    async def fake_stream(
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        assert messages
        raise LLMGenerationTimeoutError("read timed out")
        yield TextDeltaEvent(text="unreachable")

    monkeypatch.setattr(
        "app.routers.chat.stream_chat_with_llm",
        fake_stream,
    )

    response = client.post(
        "/v1/chat/stream",
        headers={"x-api-key": settings.api_key},
        json=_payload(),
    )

    assert response.status_code == 200
    assert json.loads(response.text) == {
        "type": "error",
        "code": "LLM_GENERATION_TIMEOUT",
        "message": "LLM generation timed out",
        "retryable": False,
    }
