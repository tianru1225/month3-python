import asyncio
import inspect
import json
from typing import Any

import httpx
import pytest

from app.config import settings
from app.routers.chat import create_chat
from app.schemas.chat import ChatMessage, ChatResult
from app.services.errors import LLMUpstreamError
from app.services.llm_service import chat_with_llm


def valid_payload() -> dict[str, list[dict[str, str]]]:
    return {
        "messages": [
            {
                "role": "user",
                "content": "只回答,DAY097_OK",
            }
        ]
    }


def ollama_response_json() -> dict[str, Any]:
    return {
        "model": "qwen2.5:3b",
        "message": {
            "role": "assistant",
            "content": "DAY097_OK",
        },
        "done": True,
        "done_reason": "stop",
    }


def test_chat_functions_are_coroutines() -> None:
    assert inspect.iscoroutinefunction(chat_with_llm)
    assert inspect.iscoroutinefunction(create_chat)


def test_chat_requires_api_key(client):
    response = client.post("/v1/chat", json=valid_payload())

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "API_KEY_MISSING"


def test_chat_rejects_invalid_api_key(client):
    response = client.post(
        "/v1/chat",
        headers={"x-api-key": "wrong-key"},
        json=valid_payload(),
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "API_KEY_INVALID"


def test_chat_returns_unified_response(client, monkeypatch):
    async def fake_chat(messages: list[ChatMessage]) -> ChatResult:
        return ChatResult(
            model="qwen2.5:3b",
            message=ChatMessage(
                role="assistant",
                content="DAY097_OK",
            ),
            finish_reason="stop",
        )

    monkeypatch.setattr(
        "app.routers.chat.chat_with_llm",
        fake_chat,
    )

    response = client.post(
        "/v1/chat",
        headers={"x-api-key": settings.api_key},
        json=valid_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["msg"] == "success"
    assert body["data"]["model"] == "qwen2.5:3b"
    assert body["data"]["message"]["role"] == "assistant"
    assert body["data"]["message"]["content"] == "DAY097_OK"
    assert body["data"]["finish_reason"] == "stop"


def test_service_sends_async_request() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        captured["timeout"] = request.extensions["timeout"]
        return httpx.Response(200, json=ollama_response_json())

    async def run() -> ChatResult:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as injected:
            return await chat_with_llm(
                [ChatMessage(role="user", content="hello")],
                client=injected,
            )

    result = asyncio.run(run())

    assert result.model == "qwen2.5:3b"
    assert result.message.role == "assistant"
    assert result.message.content == "DAY097_OK"
    assert result.finish_reason == "stop"

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["model"] == settings.ollama_model
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["options"]["num_ctx"] == 4096
    assert captured["payload"]["options"]["num_predict"] == 300
    assert captured["timeout"]["connect"] == 10.0
    assert captured["timeout"]["read"] == 240.0


def test_service_translates_httpx_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    async def run() -> ChatResult:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as injected:
            return await chat_with_llm(
                [ChatMessage(role="user", content="hello")],
                client=injected,
            )

    with pytest.raises(LLMUpstreamError) as exc_info:
        asyncio.run(run())

    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)


def test_router_converts_service_error_to_502(client, monkeypatch):
    async def failing_chat(messages: list[ChatMessage]) -> ChatResult:
        raise LLMUpstreamError("upstream unavailable")

    monkeypatch.setattr(
        "app.routers.chat.chat_with_llm",
        failing_chat,
    )

    response = client.post(
        "/v1/chat",
        headers={"x-api-key": settings.api_key},
        json=valid_payload(),
    )

    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["code"] == "LLM_UPSTREAM_ERROR"
    assert body["detail"]["message"] == "LLM upstream request failed"


def test_chat_rejects_empty_messages(client):
    response = client.post(
        "/v1/chat",
        headers={"x-api-key": settings.api_key},
        json={"messages": []},
    )

    assert response.status_code == 422


def test_openapi_contains_chat_path(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/v1/chat" in response.json()["paths"]
    assert "post" in response.json()["paths"]["/v1/chat"]