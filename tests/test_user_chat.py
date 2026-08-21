import json
from collections.abc import AsyncIterator

from sqlalchemy import select

from app.config import settings
from app.models.user import User
from app.schemas.chat import ChatMessage, ChatResult
from app.schemas.llm_stream import (
    DoneEvent,
    StreamEvent,
    TextDeltaEvent,
    UsageEvent,
)


def register(client, username: str, password: str = "day120-user-chat-password"):
    return client.post(
        "/users",
        json={"username": username, "password": password},
    )


def login(client, username: str, password: str = "day120-user-chat-password"):
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )


def token_for(client, username: str = "chat-user") -> str:
    assert register(client, username).status_code == 201
    response = login(client, username)
    assert response.status_code == 200
    return response.json()["access_token"]


def valid_payload() -> dict[str, list[dict[str, str]]]:
    return {
        "messages": [
            {
                "role": "user",
                "content": "Only answer USER_CHAT_OK",
            }
        ]
    }


def test_user_chat_requires_jwt(client) -> None:
    response = client.post("/v1/user-chat", json=valid_payload())

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"


def test_user_chat_does_not_accept_api_key_as_user_identity(client) -> None:
    response = client.post(
        "/v1/user-chat",
        headers={"x-api-key": settings.api_key},
        json=valid_payload(),
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"


def test_user_chat_returns_result_for_active_jwt_user(client, monkeypatch) -> None:
    token = token_for(client)

    async def fake_chat(messages: list[ChatMessage]) -> ChatResult:
        assert messages
        return ChatResult(
            model="qwen3.8-max",
            message=ChatMessage(role="assistant", content="USER_CHAT_OK"),
            finish_reason="stop",
        )

    monkeypatch.setattr("app.routers.chat.chat_with_llm", fake_chat)

    response = client.post(
        "/v1/user-chat",
        headers={"Authorization": f"Bearer {token}"},
        json=valid_payload(),
    )

    assert response.status_code == 200
    assert response.json()["data"]["message"]["content"] == "USER_CHAT_OK"


def test_user_chat_rejects_invalid_jwt(client) -> None:
    response = client.post(
        "/v1/user-chat",
        headers={"Authorization": "Bearer invalid-token"},
        json=valid_payload(),
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_INVALID"


def test_user_chat_rejects_disabled_user_after_token_issue(
    client,
    db_session,
) -> None:
    token = token_for(client, "disabled-chat-user")
    user = db_session.scalar(select(User).where(User.username == "disabled-chat-user"))

    assert user is not None

    user.status = "DISABLED"
    db_session.commit()

    response = client.post(
        "/v1/user-chat",
        headers={"Authorization": f"Bearer {token}"},
        json=valid_payload(),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "USER_NOT_ACTIVE"


def test_user_chat_stream_requires_jwt(client) -> None:
    response = client.post("/v1/user-chat/stream", json=valid_payload())

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"


def test_user_chat_stream_returns_ndjson_for_active_user(
    client,
    monkeypatch,
) -> None:
    token = token_for(client, "stream-chat-user")

    async def fake_stream(
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        assert messages
        yield TextDeltaEvent(text="USER")
        yield UsageEvent(input_tokens=4, output_tokens=2)
        yield DoneEvent(finish_reason="stop")

    monkeypatch.setattr(
        "app.routers.chat.stream_chat_with_llm",
        fake_stream,
    )

    response = client.post(
        "/v1/user-chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json=valid_payload(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    assert [json.loads(line) for line in response.text.splitlines()] == [
        {
            "type": "text_delta",
            "text": "USER",
        },
        {
            "type": "usage",
            "input_tokens": 4,
            "output_tokens": 2,
            "cached_input_tokens": None,
        },
        {
            "type": "done",
            "finish_reason": "stop",
        },
    ]


def test_user_chat_paths_are_in_openapi(client) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    paths = response.json()["paths"]

    assert "post" in paths["/v1/user-chat"]
    assert "post" in paths["/v1/user-chat/stream"]
