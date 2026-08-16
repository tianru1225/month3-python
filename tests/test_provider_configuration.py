import asyncio
import logging
import traceback
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings, settings
from app.providers import (
    Capability,
    ModelRequest,
    ProviderAuthenticationError,
)
from app.providers.qwen_adapter import QwenAdapter
from app.schemas.chat import ChatMessage


def model_request() -> ModelRequest:
    return ModelRequest(
        model="qwen3.8-max",
        messages=[ChatMessage(role="user", content="configuration test")],
        required_capabilities=frozenset({Capability.CHAT}),
        max_output_tokens=20,
    )


def test_dashscope_api_key_is_redacted_in_settings() -> None:
    secret = "day115-secret-value"
    configured = Settings(
        _env_file=None,
        dashscope_api_key=secret,
    )

    assert isinstance(configured.dashscope_api_key, SecretStr)
    assert configured.dashscope_api_key.get_secret_value() == secret
    assert secret not in repr(configured)
    assert secret not in str(configured.model_dump())


def test_assignment_keeps_dashscope_api_key_secret() -> None:
    configured = Settings(_env_file=None)

    configured.dashscope_api_key = "rotated-secret"

    assert isinstance(configured.dashscope_api_key, SecretStr)
    assert configured.dashscope_api_key.get_secret_value() == "rotated-secret"
    assert "rotated-secret" not in repr(configured)


def test_missing_dashscope_api_key_is_rejected_before_request(monkeypatch) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, request=request)

    monkeypatch.setattr(settings, "dashscope_api_key", "")

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ValueError) as exc_info:
                QwenAdapter(client=client)

        assert str(exc_info.value) == "DASHSCOPE_API_KEY must not be empty"

    asyncio.run(run())

    assert request_count == 0


def test_qwen_authentication_failure_does_not_expose_key(
    monkeypatch,
    caplog,
) -> None:
    secret = "day115-provider-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {secret}"
        return httpx.Response(
            401,
            json={"error": {"message": "authentication failed"}},
            request=request,
        )

    monkeypatch.setattr(settings, "dashscope_api_key", secret)

    async def run() -> ProviderAuthenticationError:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = QwenAdapter(client=client)
            with pytest.raises(ProviderAuthenticationError) as exc_info:
                await adapter.provider.complete(model_request())
            return exc_info.value

    with caplog.at_level(logging.INFO):
        error = asyncio.run(run())

    formatted_exception = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    assert secret not in repr(settings)
    assert secret not in str(error)
    assert secret not in formatted_exception
    assert secret not in caplog.text


def test_env_example_contains_only_dashscope_placeholder() -> None:
    lines = dict(
        line.split("=", 1)
        for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )

    assert lines["DASHSCOPE_API_KEY"] == "replace-me"
