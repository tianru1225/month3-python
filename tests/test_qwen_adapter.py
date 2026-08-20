import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.providers import (
    Capability,
    ModelRequest,
    ProviderExecutionError,
)
from app.providers.qwen_adapter import (
    QwenAdapter,
)
from app.schemas.chat import ChatMessage
from app.schemas.llm_stream import (
    DoneEvent,
    TextDeltaEvent,
    UsageEvent,
)


def build_request(
    *,
    response_schema: (dict[str, Any] | None) = None,
) -> ModelRequest:
    capabilities = {
        Capability.CHAT,
        Capability.USAGE,
    }

    if response_schema is not None:
        capabilities.add(Capability.STRUCTURED_OUTPUT)

    return ModelRequest(
        model="qwen3.8-max",
        messages=[
            ChatMessage(
                role="user",
                content=("Return a learning task."),
            )
        ],
        required_capabilities=frozenset(capabilities),
        response_schema=response_schema,
        max_output_tokens=200,
    )


def build_stream_request() -> ModelRequest:
    return ModelRequest(
        model="qwen3.8-max",
        messages=[
            ChatMessage(
                role="user",
                content=("Explain async streams."),
            )
        ],
        required_capabilities=frozenset(
            {
                Capability.CHAT,
                Capability.STREAMING,
                Capability.USAGE,
            }
        ),
        max_output_tokens=200,
    )


def response_body(
    *,
    content: str,
) -> dict[str, Any]:
    return {
        "model": "qwen3.8-max",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 21,
            "completion_tokens": 13,
            "total_tokens": 34,
            "prompt_tokens_details": {
                "cached_tokens": 4,
            },
        },
    }


def test_adapter_maps_qwen_result_and_usage() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == ("https://qwen.test/v1/chat/completions")
        assert request.headers["authorization"] == "Bearer test-key"

        payload = json.loads(request.read())

        assert payload["stream"] is False
        assert payload["model"] == ("qwen3.8-max")
        assert payload["max_completion_tokens"] == 200
        assert "max_tokens" not in payload

        return httpx.Response(
            200,
            json=response_body(
                content=("A structured learning task."),
            ),
            request=request,
        )

    async def run() -> Any:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url=("https://qwen.test/v1"),
            )

            return await adapter.provider.complete(build_request())

    result = asyncio.run(run())

    assert result.provider == "qwen"
    assert result.model == "qwen3.8-max"
    assert result.message.role == "assistant"
    assert result.message.content == ("A structured learning task.")
    assert result.finish_reason == "stop"
    assert result.usage is not None
    assert result.usage.input_tokens == 21
    assert result.usage.output_tokens == 13
    assert result.usage.cached_input_tokens == 4
    assert result.usage.total_tokens == 34


def test_adapter_sends_json_schema_and_parses_output() -> None:
    schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
            },
            "estimated_minutes": {
                "type": "integer",
            },
        },
        "required": [
            "title",
            "estimated_minutes",
        ],
        "additionalProperties": False,
    }

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(request.read())

        assert payload["response_format"] == {
            "type": "json_schema",
            "json_schema": {
                "name": ("structured_response"),
                "schema": schema,
                "strict": True,
            },
        }

        return httpx.Response(
            200,
            json=response_body(
                content=('{"title":"Async retry","estimated_minutes":60}'),
            ),
            request=request,
        )

    async def run() -> Any:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url=("https://qwen.test/v1"),
            )

            return await adapter.provider.complete(
                build_request(
                    response_schema=schema,
                )
            )

    result = asyncio.run(run())

    assert result.structured_output == {
        "title": "Async retry",
        "estimated_minutes": 60,
    }


def test_invalid_structured_response_is_hidden_by_provider_boundary() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=response_body(
                content='{"title":',
            ),
            request=request,
        )

    async def run() -> Any:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url=("https://qwen.test/v1"),
            )

            with pytest.raises(ProviderExecutionError) as exc_info:
                await adapter.provider.complete(
                    build_request(
                        response_schema={
                            "type": "object",
                        }
                    )
                )

            return exc_info.value

    error = asyncio.run(run())

    assert error.provider == "qwen"
    assert "test-key" not in str(error)


def test_adapter_maps_qwen_stream_events_and_usage() -> None:
    stream_body = (
        "\n\n".join(
            [
                (
                    'data: {"choices":[{'
                    '"delta":{"role":"assistant",'
                    '"content":"Hello"},'
                    '"finish_reason":null}]}'
                ),
                (
                    'data: {"choices":[{'
                    '"delta":{"content":" world"},'
                    '"finish_reason":null}]}'
                ),
                ('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'),
                (
                    'data: {"choices":[],'
                    '"usage":{"prompt_tokens":12,'
                    '"completion_tokens":7,'
                    '"prompt_tokens_details":'
                    '{"cached_tokens":2}}}'
                ),
                "data: [DONE]",
            ]
        )
        + "\n\n"
    )

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(request.read())

        assert payload["stream"] is True
        assert payload["max_completion_tokens"] == 200
        assert "max_tokens" not in payload
        assert payload["stream_options"] == {
            "include_usage": True,
        }

        return httpx.Response(
            200,
            text=stream_body,
            headers={"content-type": ("text/event-stream")},
            request=request,
        )

    async def run() -> list[Any]:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url=("https://qwen.test/v1"),
            )

            return [
                event async for event in adapter.provider.stream(build_stream_request())
            ]

    events = asyncio.run(run())

    assert events == [
        TextDeltaEvent(text="Hello"),
        TextDeltaEvent(text=" world"),
        UsageEvent(
            input_tokens=12,
            output_tokens=7,
            cached_input_tokens=2,
        ),
        DoneEvent(finish_reason="stop"),
    ]


def test_invalid_qwen_stream_event_is_hidden_by_provider_boundary() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            text=("data: {broken-json}\n\n"),
            headers={"content-type": ("text/event-stream")},
            request=request,
        )

    async def run() -> Any:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url=("https://qwen.test/v1"),
            )

            with pytest.raises(ProviderExecutionError) as exc_info:
                async for _event in adapter.provider.stream(build_stream_request()):
                    raise AssertionError("invalid stream must not emit events")

            return exc_info.value

    error = asyncio.run(run())

    assert error.provider == "qwen"
    assert "test-key" not in str(error)


def test_stream_cancellation_closes_upstream_response() -> None:
    class BlockingStream(httpx.AsyncByteStream):
        def __init__(self) -> None:
            self.waiting = asyncio.Event()
            self.closed = False

        async def __aiter__(
            self,
        ) -> AsyncIterator[bytes]:
            yield (
                b'data: {"choices":[{'
                b'"delta":{"content":"hello"},'
                b'"finish_reason":null}]}\n\n'
            )

            self.waiting.set()

            await asyncio.Future()

        async def aclose(self) -> None:
            self.closed = True

    upstream_stream = BlockingStream()

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": ("text/event-stream")},
            stream=upstream_stream,
            request=request,
        )

    async def run() -> bool:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url=("https://qwen.test/v1"),
            )

            async def consume() -> None:
                async for _event in adapter.provider.stream(build_stream_request()):
                    continue

            task = asyncio.create_task(consume())

            await upstream_stream.waiting.wait()

            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

        return upstream_stream.closed

    assert asyncio.run(run()) is True
