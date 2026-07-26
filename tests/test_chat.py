from typing import Any

import httpx
import pytest

from app.config import settings
from app.schemas.chat import ChatMessage
from app.services.errors import LLMUpstreamError
from app.services.llm_service import chat_with_llm

def valid_payload() -> dict[str,list[dict[str,str]]]:
    return {
        "messages":[
            {
                "role":"user",
                "content":"只回答,DAY96_OK",
            }
        ]
    }

def test_chat_requires_api_Key(client):
    response = client.post("/v1/chat",json = valid_payload())

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "API_KEY_MISSING"

def test_chat_returns_unified_response(client,monkeypatch):
    captured: dict[str,Any] = {}
    def fake_post(url:str,*,json:dict[str,Any],timeout: httpx.Timeout) -> httpx.Response:
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            request = httpx.Request("POST",url),
            json = {
                "model": "qwen2.5:3b",
                "message": {
                    "role": "assistant",
                    "content": "DAY096_OK"
                },
                "done": True,
                "done_reason": "stop",
            },  
        )
    monkeypatch.setattr(
        "app.services.llm_service.httpx.post",
        fake_post,
    )
    response = client.post("/v1/chat",headers={"x-api-key": settings.api_key},json=valid_payload())
    body  =response.json()
    assert body["code"] == "OK"
    assert body["msg"] == "success"
    assert body["data"]["model"] == "qwen2.5:3b"
    assert body["data"]["message"]["role"] == "assistant"
    assert body["data"]["message"]["content"] == "DAY096_OK"
    assert body["data"]["finish_reason"] == "stop"
    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["model"] == settings.ollama_model
    assert captured["json"]["stream"] is False
    assert captured["json"]["options"]["num_predict"] == 300
    
    timeout = captured["timeout"]
    assert isinstance(timeout,httpx.Timeout)
    assert timeout.connect == 10.0
    assert timeout.read == 240.0

def test_service_translates_httpx_error(monkeypatch):
    def failing_post(url: str,*,json: dict[str,Any],timeout: httpx.Timeout) -> httpx.Response:
        request = httpx.Request("POST",url)
        raise httpx.ConnectError("connection failed",request = request)

    monkeypatch.setattr(
        "app.services.llm_service.httpx.post",
        failing_post,
    )

    messages=[
        ChatMessage(
            role="user",
            content="hello",
        )
    ]

    with pytest.raises(LLMUpstreamError):
        chat_with_llm(messages)

def test_router_converts_service_error_to_502(client,monkeypatch):
    def failing_chat(messages: list[ChatMessage]) -> None:
        raise LLMUpstreamError("upstream unavailable")
    monkeypatch.setattr(
        "app.routers.chat.chat_with_llm",
        failing_chat,
    )

    response = client.post(
        "/v1/chat",
        headers = {"x-api-key": settings.api_key},
        json=valid_payload(),
    )
    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["code"] == "LLM_UPSTREAM_ERROR"
    assert body["detail"]["message"] == "LLM upstream request failed"

def test_chat_rejects_empty_messages(client):
    response = client.post(
        "/v1/chat",
        headers={"x-api-key":settings.api_key},
        json = {"messages":[]},
    )

    assert response.status_code == 422

def test_openapi_contains_chat_path(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/v1/chat" in response.json()["paths"]
    assert "post" in response.json()["paths"]["/v1/chat"]