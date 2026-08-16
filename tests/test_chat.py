import asyncio
import inspect
import json
from typing import Any

import httpx
import pytest

from app.config import settings
from app.routers.chat import create_chat
from app.schemas.chat import ChatMessage, ChatResult
from app.services.errors import (
    LLMRequestTimeoutError,
    LLMUpstreamConnectionError,
    LLMUpstreamError,
)
from app.services.llm_service import chat_with_llm


def valid_payload() -> dict[str, list[dict[str, str]]]:
    return {
        "messages": [
            {
                "role": "user",
                "content": "Only answer DAY113_OK",
            }
        ]
    }


def qwen_response_json() -> dict[str, Any]:
    return {
        "model": "qwen3.8-max",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "DAY113_OK",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 3,
        },
    }


def test_chat_functions_are_coroutines() -> None:
    assert inspect.iscoroutinefunction(chat_with_llm)
    assert inspect.iscoroutinefunction(create_chat)


def test_chat_requires_api_key(client) -> None:
    response = client.post("/v1/chat", json=valid_payload())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "API_KEY_MISSING"


def test_chat_rejects_invalid_api_key(client) -> None:
    response = client.post(
        "/v1/chat",
        headers={"x-api-key": "wrong-key"},
        json=valid_payload(),
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "API_KEY_INVALID"


def test_chat_returns_unified_response(client, monkeypatch) -> None:
    async def fake_chat(messages: list[ChatMessage]) -> ChatResult:
        assert messages
        return ChatResult(
            model="qwen3.8-max",
            message=ChatMessage(role="assistant", content="DAY113_OK"),
            finish_reason="stop",
        )

    monkeypatch.setattr("app.routers.chat.chat_with_llm", fake_chat)

    response = client.post(
        "/v1/chat",
        headers={"x-api-key": settings.api_key},
        json=valid_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["msg"] == "success"
    assert body["data"]["model"] == "qwen3.8-max"
    assert body["data"]["message"] == {
        "role": "assistant",
        "content": "DAY113_OK",
    }
    assert body["data"]["finish_reason"] == "stop"


def test_service_sends_qwen_request(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        captured["timeout"] = request.extensions["timeout"]
        return httpx.Response(200, json=qwen_response_json(), request=request)

    monkeypatch.setattr(settings, "dashscope_api_key", "test-key")
    monkeypatch.setattr(settings, "qwen_max_output_tokens", 300)

    async def run() -> ChatResult:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as injected:
            return await chat_with_llm(
                [ChatMessage(role="user", content="hello")],
                client=injected,
            )

    result = asyncio.run(run())

    assert result.model == "qwen3.8-max"
    assert result.message.content == "DAY113_OK"
    assert result.finish_reason == "stop"
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/compatible-mode/v1/chat/completions")
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == settings.qwen_model
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["max_tokens"] == 300
    assert captured["timeout"] == {
        "connect": settings.qwen_connect_timeout_seconds,
        "read": settings.qwen_read_timeout_seconds,
        "write": settings.qwen_write_timeout_seconds,
        "pool": settings.qwen_pool_timeout_seconds,
    }


def test_service_translates_qwen_unavailable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"}, request=request)

    monkeypatch.setattr(settings, "dashscope_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_retry_max_attempts", 1)

    async def run() -> ChatResult:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as injected:
            return await chat_with_llm(
                [ChatMessage(role="user", content="hello")],
                client=injected,
            )

    with pytest.raises(LLMUpstreamConnectionError) as exc_info:
        asyncio.run(run())

    assert exc_info.value.code == "LLM_UPSTREAM_CONNECTION_ERROR"


def test_router_converts_service_error_to_502(client, monkeypatch) -> None:
    async def failing_chat(messages: list[ChatMessage]) -> ChatResult:
        raise LLMUpstreamError("upstream unavailable")

    monkeypatch.setattr("app.routers.chat.chat_with_llm", failing_chat)

    response = client.post(
        "/v1/chat",
        headers={"x-api-key": settings.api_key},
        json=valid_payload(),
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "LLM_UPSTREAM_ERROR",
        "message": "LLM upstream request failed",
    }


def test_router_converts_service_timeout_to_504(client, monkeypatch) -> None:
    async def failing_chat(messages: list[ChatMessage]) -> ChatResult:
        raise LLMRequestTimeoutError("upstream timed out")

    monkeypatch.setattr("app.routers.chat.chat_with_llm", failing_chat)

    response = client.post(
        "/v1/chat",
        headers={"x-api-key": settings.api_key},
        json=valid_payload(),
    )

    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "LLM_REQUEST_TIMEOUT"


def test_chat_rejects_empty_messages(client) -> None:
    response = client.post(
        "/v1/chat",
        headers={"x-api-key": settings.api_key},
        json={"messages": []},
    )
    assert response.status_code == 422


def test_openapi_contains_chat_path(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "post" in response.json()["paths"]["/v1/chat"]
