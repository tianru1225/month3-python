import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from app.providers import (
    Capability,
    ModelRequest,
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.qwen_adapter import (
    QwenAdapter,
)
from app.schemas.chat import ChatMessage
from app.schemas.llm_stream import StreamEvent


def build_request(
    *,
    streaming: bool = False,
) -> ModelRequest:
    capabilities = {
        Capability.CHAT,
    }

    if streaming:
        capabilities.add(Capability.STREAMING)

    return ModelRequest(
        model="qwen3.8-max",
        messages=[
            ChatMessage(
                role="user",
                content="Quality probe",
            )
        ],
        required_capabilities=frozenset(capabilities),
        max_output_tokens=20,
    )


@pytest.mark.parametrize(
    (
        "status_code",
        "error_type",
        "retryable",
    ),
    [
        (
            401,
            ProviderAuthenticationError,
            False,
        ),
        (
            429,
            ProviderRateLimitError,
            True,
        ),
        (
            503,
            ProviderUnavailableError,
            True,
        ),
    ],
)
def test_qwen_http_status_is_mapped(
    status_code: int,
    error_type: type[ProviderError],
    retryable: bool,
) -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={
                "error": {
                    "message": ("secret upstream detail"),
                }
            },
            request=request,
        )

    async def run() -> ProviderError:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url=("https://qwen.test/v1"),
            )

            with pytest.raises(error_type) as exc_info:
                await adapter.provider.complete(build_request())

            return exc_info.value

    error = asyncio.run(run())

    assert error.provider == "qwen"
    assert error.retryable is retryable
    assert "secret" not in str(error)
    assert "test-key" not in str(error)


def test_qwen_complete_timeout_is_mapped_without_retry() -> None:
    call_count = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal call_count
        call_count += 1

        raise httpx.ReadTimeout(
            "upstream timed out",
            request=request,
        )

    async def run() -> ProviderTimeoutError:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url=("https://qwen.test/v1"),
            )

            with pytest.raises(ProviderTimeoutError) as exc_info:
                await adapter.provider.complete(build_request())

            return exc_info.value

    error = asyncio.run(run())

    assert call_count == 1
    assert error.provider == "qwen"
    assert error.retryable is True


def test_qwen_stream_timeout_is_mapped_without_retry() -> None:
    call_count = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal call_count
        call_count += 1

        raise httpx.ReadTimeout(
            "upstream timed out",
            request=request,
        )

    async def run() -> ProviderTimeoutError:
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            adapter = QwenAdapter(
                client=client,
                api_key="test-key",
                base_url=("https://qwen.test/v1"),
            )

            with pytest.raises(ProviderTimeoutError) as exc_info:
                stream: AsyncIterator[StreamEvent] = adapter.provider.stream(
                    build_request(streaming=True)
                )

                async for _event in stream:
                    raise AssertionError("timeout must not emit events")

            return exc_info.value

    error = asyncio.run(run())

    assert call_count == 1
    assert error.provider == "qwen"
    assert error.retryable is True
