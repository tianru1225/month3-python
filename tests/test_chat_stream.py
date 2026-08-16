import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
from app.core.concurrency import ProviderConcurrencyLimiter
from app.routers.chat import _stream_as_ndjson
from app.schemas.chat import ChatMessage
from app.schemas.llm_stream import (
    DoneEvent,
    StreamEvent,
    TextDeltaEvent,
    UsageEvent,
)
from app.services.errors import LLMUpstreamError
from app.services.llm_service import stream_chat_with_llm


def valid_payload() -> dict[str, list[dict[str, str]]]:
    return {
        "messages": [
            {
                "role": "user",
                "content": "Only answer STREAM_OK",
            }
        ]
    }


def test_stream_service_sends_qwen_request_and_parses_events(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    stream_body = "\n\n".join(
        [
            (
                'data: {"choices":[{"delta":{"content":"STREAM"},'
                '"finish_reason":null}]}'
            ),
            (
                'data: {"choices":[{"delta":{"content":"_OK"},'
                '"finish_reason":null}]}'
            ),
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            (
                'data: {"choices":[],"usage":{"prompt_tokens":10,'
                '"completion_tokens":2,'
                '"prompt_tokens_details":{"cached_tokens":1}}}'
            ),
            'data: {"choices":[],"usage":null}',
            "data: [DONE]",
        ]
    ) + "\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            text=stream_body,
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    monkeypatch.setattr(settings, "dashscope_api_key", "test-key")

    async def run() -> list[StreamEvent]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as injected:
            return [
                event
                async for event in stream_chat_with_llm(
                    [ChatMessage(role="user", content="hello")],
                    client=injected,
                )
            ]

    events = asyncio.run(run())

    assert events == [
        TextDeltaEvent(text="STREAM"),
        TextDeltaEvent(text="_OK"),
        UsageEvent(
            input_tokens=10,
            output_tokens=2,
            cached_input_tokens=1,
        ),
        DoneEvent(finish_reason="stop"),
    ]
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/compatible-mode/v1/chat/completions")
    assert captured["payload"]["model"] == settings.qwen_model
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["stream_options"] == {"include_usage": True}


class BlockingQwenStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield (
            b'data: {"choices":[{"delta":{"content":"first"},'
            b'"finish_reason":null}]}\n\n'
        )
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed.set()


def test_closing_service_stream_releases_qwen_response_and_permit(
    monkeypatch,
) -> None:
    async def run() -> None:
        body = BlockingQwenStream()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=body,
                request=request,
            )

        monkeypatch.setattr(settings, "dashscope_api_key", "test-key")
        limiter = ProviderConcurrencyLimiter(max_active=1, max_waiting=0)
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(transport=transport) as injected:
            stream = stream_chat_with_llm(
                [ChatMessage(role="user", content="hello")],
                client=injected,
                limiter=limiter,
            )

            first = await anext(stream)
            assert first == TextDeltaEvent(text="first")
            assert limiter.snapshot.active == 1

            await stream.aclose()
            await asyncio.wait_for(body.closed.wait(), timeout=1.0)

            assert limiter.snapshot.active == 0
            assert limiter.snapshot.waiting == 0

    asyncio.run(run())


def test_stream_endpoint_returns_ndjson(client, monkeypatch) -> None:
    async def fake_stream(
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        assert messages
        yield TextDeltaEvent(text="STREAM_OK")
        yield UsageEvent(input_tokens=8, output_tokens=2)
        yield DoneEvent(finish_reason="stop")

    monkeypatch.setattr("app.routers.chat.stream_chat_with_llm", fake_stream)

    response = client.post(
        "/v1/chat/stream",
        headers={"x-api-key": settings.api_key},
        json=valid_payload(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert [json.loads(line) for line in response.text.splitlines()] == [
        {
            "type": "text_delta",
            "text": "STREAM_OK",
        },
        {
            "type": "usage",
            "input_tokens": 8,
            "output_tokens": 2,
            "cached_input_tokens": None,
        },
        {
            "type": "done",
            "finish_reason": "stop",
        },
    ]


def test_stream_endpoint_returns_terminal_error_event(client, monkeypatch) -> None:
    async def failing_stream(
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        if messages:
            raise LLMUpstreamError("upstream unavailable")
        yield DoneEvent(finish_reason="stop")

    monkeypatch.setattr("app.routers.chat.stream_chat_with_llm", failing_stream)

    response = client.post(
        "/v1/chat/stream",
        headers={"x-api-key": settings.api_key},
        json=valid_payload(),
    )

    assert response.status_code == 200
    assert json.loads(response.text) == {
        "type": "error",
        "code": LLMUpstreamError.code,
        "message": LLMUpstreamError.public_message,
        "retryable": LLMUpstreamError.retryable,
    }


def test_closing_route_stream_closes_service_generator(
    monkeypatch,
    caplog,
) -> None:
    async def run() -> None:
        upstream_closed = asyncio.Event()

        async def fake_stream(
            messages: list[ChatMessage],
        ) -> AsyncIterator[StreamEvent]:
            assert messages
            try:
                yield TextDeltaEvent(text="first")
                await asyncio.Event().wait()
            finally:
                upstream_closed.set()

        monkeypatch.setattr("app.routers.chat.stream_chat_with_llm", fake_stream)
        iterator = _stream_as_ndjson(
            [ChatMessage(role="user", content="hello")],
            request_id="day113-test",
        )

        first = await anext(iterator)
        assert '"type":"text_delta"' in first
        await iterator.aclose()
        await asyncio.wait_for(upstream_closed.wait(), timeout=1.0)

    with caplog.at_level(logging.INFO, logger="app.chat_stream"):
        asyncio.run(run())

    assert "request_id=day113-test outcome=cancelled" in caplog.text


def test_stream_endpoint_requires_api_key(client) -> None:
    response = client.post("/v1/chat/stream", json=valid_payload())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "API_KEY_MISSING"