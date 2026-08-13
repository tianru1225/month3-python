import asyncio
from typing import Any

import httpx
import pytest

from app.providers import (
    Capability,
    ModelRequest,
    ProviderExecutionError,
)
from app.providers.qwen_adapter import QwenAdapter
from app.schemas.chat import ChatMessage


def build_request(
    *,
    response_schema: dict[str, Any] | None = None,
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
                content="Return a learning task.",
            )
        ],
        required_capabilities=frozenset(capabilities),
        response_schema=response_schema,
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
        assert request.headers["authorization"] == ("Bearer test-key")

        payload = request.read()
        assert b'"stream":false' in payload

        return httpx.Response(
            200,
            json=response_body(
                content="A structured learning task.",
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
                base_url="https://qwen.test/v1",
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
        payload = request.read().decode("utf-8")
        assert '"type":"json_schema"' in payload
        assert '"strict":true' in payload
        assert '"title"' in payload
        assert '"estimated_minutes"' in payload

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
                base_url="https://qwen.test/v1",
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
                base_url="https://qwen.test/v1",
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
