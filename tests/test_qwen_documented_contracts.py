import asyncio
import json
from typing import Any

import httpx

from app.providers import Capability, ModelRequest
from app.providers.qwen_adapter import QwenAdapter
from app.schemas.chat import ChatMessage


def test_structured_request_omits_max_tokens() -> None:
    captured_payload: dict[str, Any] = {}
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
        },
        "required": ["title"],
        "additionalProperties": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3.8-max",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"title":"Async streams"}',
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
            },
            request=request,
        )

    async def run() -> dict[str, Any] | None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url="https://qwen.test/v1",
            )
            result = await adapter.provider.complete(
                ModelRequest(
                    model="qwen3.8-max",
                    messages=[
                        ChatMessage(
                            role="user",
                            content="Return a structured task",
                        )
                    ],
                    required_capabilities=frozenset(
                        {
                            Capability.CHAT,
                            Capability.STRUCTURED_OUTPUT,
                        }
                    ),
                    response_schema=schema,
                    max_output_tokens=200,
                )
            )
            return result.structured_output

    structured_output = asyncio.run(run())

    assert captured_payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "structured_response",
            "schema": schema,
            "strict": True,
        },
    }
    assert "max_tokens" not in captured_payload
    assert structured_output == {"title": "Async streams"}
    assert "max_tokens" not in captured_payload
    assert "max_completion_tokens" not in captured_payload
