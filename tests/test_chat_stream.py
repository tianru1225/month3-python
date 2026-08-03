import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
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


def test_stream_service_sends_request_and_parses_events() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)

        content = (
            '{"message":{"content":"STREAM"},"done":false}\n'
            '{"message":{"content":"_OK"},"done":false}\n'
            '{"message":{"content":""},"done":true,'
            '"done_reason":"stop",'
            '"prompt_eval_count":10,"eval_count":2}\n'
        )

        return httpx.Response(
            200,
            headers={
                "content-type": "application/x-ndjson",
            },
            content=content,
        )

    async def run() -> list[StreamEvent]:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as injected:
            return [
                event
                async for event in stream_chat_with_llm(
                    [
                        ChatMessage(
                            role="user",
                            content="hello",
                        )
                    ],
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
        ),
        DoneEvent(finish_reason="stop"),
    ]

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["model"] == settings.ollama_model
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["options"]["num_ctx"] == 4096
    assert captured["payload"]["options"]["num_predict"] == 300


def test_stream_endpoint_returns_ndjson(
    client,
    monkeypatch,
) -> None:
    async def fake_stream(
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        assert messages
        yield TextDeltaEvent(text="STREAM_OK")
        yield UsageEvent(
            input_tokens=8,
            output_tokens=2,
        )
        yield DoneEvent(finish_reason="stop")

    monkeypatch.setattr(
        "app.routers.chat.stream_chat_with_llm",
        fake_stream,
    )

    response = client.post(
        "/v1/chat/stream",
        headers={
            "x-api-key": settings.api_key,
        },
        json=valid_payload(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    body = [json.loads(line) for line in response.text.splitlines()]

    assert body == [
        {
            "type": "text_delta",
            "text": "STREAM_OK",
        },
        {
            "type": "usage",
            "input_tokens": 8,
            "output_tokens": 2,
        },
        {
            "type": "done",
            "finish_reason": "stop",
        },
    ]


def test_stream_endpoint_returns_terminal_error_event(
    client,
    monkeypatch,
) -> None:
    async def failing_stream(
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        if messages:
            raise LLMUpstreamError("upstream unavailable")

        yield DoneEvent(finish_reason="stop")

    monkeypatch.setattr(
        "app.routers.chat.stream_chat_with_llm",
        failing_stream,
    )

    response = client.post(
        "/v1/chat/stream",
        headers={
            "x-api-key": settings.api_key,
        },
        json=valid_payload(),
    )

    assert response.status_code == 200

    assert json.loads(response.text) == {
        "type": "error",
        "code": "LLM_UPSTREAM_ERROR",
        "message": "LLM 上游流式请求失败",
        "retryable": False,
    }


def test_stream_endpoint_requires_api_key(client) -> None:
    response = client.post(
        "/v1/chat/stream",
        json=valid_payload(),
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == ("API_KEY_MISSING")
