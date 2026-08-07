import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.config import settings
from app.schemas.chat import ChatMessage, ChatResult
from app.schemas.llm_stream import TextDeltaEvent
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


def _success_json() -> dict[str, Any]:
    return {
        "model": "qwen2.5:3b",
        "message": {
            "role": "assistant",
            "content": "RETRY_OK",
        },
        "done": True,
        "done_reason": "stop",
    }


def test_retries_429_using_retry_after(
    monkeypatch,
) -> None:
    request_count = 0
    slept: list[float] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        if request_count == 1:
            return httpx.Response(
                429,
                headers={
                    "Retry-After": "2",
                },
                json={
                    "error": "rate limited",
                },
            )

        return httpx.Response(
            200,
            json=_success_json(),
        )

    async def fake_sleep(
        delay_seconds: float,
    ) -> None:
        slept.append(delay_seconds)

    monkeypatch.setattr(
        settings,
        "llm_retry_max_attempts",
        3,
    )
    monkeypatch.setattr(
        settings,
        "llm_retry_max_delay_seconds",
        8.0,
    )
    monkeypatch.setattr(
        "app.services.llm_service._sleep",
        fake_sleep,
    )

    async def run() -> ChatResult:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as injected:
            return await chat_with_llm(
                _messages(),
                client=injected,
            )

    result = asyncio.run(run())

    assert request_count == 2
    assert slept == [2.0]
    assert result.message.content == "RETRY_OK"


def test_retries_recoverable_connect_error(
    monkeypatch,
) -> None:
    request_count = 0
    slept: list[float] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        if request_count == 1:
            raise httpx.ConnectError(
                "temporary connection failure",
                request=request,
            )

        return httpx.Response(
            200,
            json=_success_json(),
        )

    async def fake_sleep(
        delay_seconds: float,
    ) -> None:
        slept.append(delay_seconds)

    monkeypatch.setattr(
        settings,
        "llm_retry_max_attempts",
        3,
    )
    monkeypatch.setattr(
        settings,
        "llm_retry_base_delay_seconds",
        0.0,
    )
    monkeypatch.setattr(
        "app.services.llm_service._sleep",
        fake_sleep,
    )

    async def run() -> ChatResult:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as injected:
            return await chat_with_llm(
                _messages(),
                client=injected,
            )

    result = asyncio.run(run())

    assert request_count == 2
    assert slept == [0.0]
    assert result.message.content == "RETRY_OK"


def test_does_not_retry_read_timeout(
    monkeypatch,
) -> None:
    request_count = 0
    slept: list[float] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ReadTimeout(
            "generation stalled",
            request=request,
        )

    async def fake_sleep(
        delay_seconds: float,
    ) -> None:
        slept.append(delay_seconds)

    monkeypatch.setattr(
        settings,
        "llm_retry_max_attempts",
        3,
    )
    monkeypatch.setattr(
        "app.services.llm_service._sleep",
        fake_sleep,
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

    with pytest.raises(LLMGenerationTimeoutError):
        asyncio.run(run())

    assert request_count == 1
    assert slept == []


class FailureAfterFirstEvent(httpx.AsyncByteStream):
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
        raise httpx.ConnectError(
            "connection dropped",
            request=self.request,
        )

    async def aclose(self) -> None:
        self.closed = True


def test_stream_does_not_retry_after_first_event(
    monkeypatch,
) -> None:
    request_count = 0
    slept: list[float] = []
    bodies: list[FailureAfterFirstEvent] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        body = FailureAfterFirstEvent(request)
        bodies.append(body)

        return httpx.Response(
            200,
            headers={"content-type": ("application/x-ndjson")},
            stream=body,
        )

    async def fake_sleep(
        delay_seconds: float,
    ) -> None:
        slept.append(delay_seconds)

    monkeypatch.setattr(
        settings,
        "llm_retry_max_attempts",
        3,
    )
    monkeypatch.setattr(
        "app.services.llm_service._sleep",
        fake_sleep,
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

            with pytest.raises(LLMUpstreamConnectionError):
                await anext(stream)

    asyncio.run(run())

    assert request_count == 1
    assert slept == []
    assert len(bodies) == 1
    assert bodies[0].closed
