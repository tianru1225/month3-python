import asyncio
from collections.abc import AsyncIterator

import pytest

from app.config import settings
from app.core.concurrency import ProviderConcurrencyLimiter
from app.providers import (
    Capability,
    ModelProvider,
    ModelRequest,
    ModelResult,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.schemas.chat import ChatMessage
from app.schemas.llm_stream import DoneEvent, StreamEvent, TextDeltaEvent
from app.services.errors import LLMConcurrencyLimitError
from app.services.provider_execution import (
    complete_with_provider,
    stream_with_provider,
)


def build_request(*, streaming: bool = False) -> ModelRequest:
    capabilities = {Capability.CHAT}
    if streaming:
        capabilities.add(Capability.STREAMING)

    return ModelRequest(
        model="fake-model",
        messages=[ChatMessage(role="user", content="hello")],
        required_capabilities=frozenset(capabilities),
    )


def build_result() -> ModelResult:
    return ModelResult(
        provider="fake",
        model="fake-model",
        message=ChatMessage(role="assistant", content="ok"),
        finish_reason="stop",
    )


def build_provider(
    complete,
    stream=None,
) -> ModelProvider:
    capabilities = {Capability.CHAT}
    if stream is not None:
        capabilities.add(Capability.STREAMING)

    return ModelProvider(
        name="fake",
        capabilities=frozenset(capabilities),
        complete=complete,
        stream=stream,
    )


def test_complete_retries_rate_limit_using_retry_after(monkeypatch) -> None:
    attempts = 0
    slept: list[float] = []

    async def complete(request: ModelRequest) -> ModelResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ProviderRateLimitError(
                provider="fake",
                retryable=True,
                retry_after_seconds=2.0,
            )
        return build_result()

    async def fake_sleep(delay_seconds: float) -> None:
        slept.append(delay_seconds)

    monkeypatch.setattr(settings, "llm_retry_max_attempts", 3)
    monkeypatch.setattr(settings, "llm_retry_max_delay_seconds", 8.0)
    monkeypatch.setattr(
        "app.services.provider_execution._sleep",
        fake_sleep,
    )

    result = asyncio.run(
        complete_with_provider(
            build_provider(complete),
            build_request(),
            limiter=ProviderConcurrencyLimiter(max_active=1, max_waiting=0),
        )
    )

    assert result.message.content == "ok"
    assert attempts == 2
    assert slept == [2.0]


def test_complete_does_not_retry_authentication_error(monkeypatch) -> None:
    attempts = 0
    slept: list[float] = []

    async def complete(request: ModelRequest) -> ModelResult:
        nonlocal attempts
        attempts += 1
        raise ProviderAuthenticationError(provider="fake")

    async def fake_sleep(delay_seconds: float) -> None:
        slept.append(delay_seconds)

    monkeypatch.setattr(settings, "llm_retry_max_attempts", 3)
    monkeypatch.setattr(
        "app.services.provider_execution._sleep",
        fake_sleep,
    )

    with pytest.raises(ProviderAuthenticationError):
        asyncio.run(
            complete_with_provider(
                build_provider(complete),
                build_request(),
                limiter=ProviderConcurrencyLimiter(max_active=1, max_waiting=0),
            )
        )

    assert attempts == 1
    assert slept == []


def test_stream_retries_before_first_event_and_closes_before_sleep(
    monkeypatch,
) -> None:
    attempts = 0
    closed_attempts: list[int] = []
    slept: list[float] = []

    async def complete(request: ModelRequest) -> ModelResult:
        return build_result()

    async def stream(request: ModelRequest) -> AsyncIterator[StreamEvent]:
        nonlocal attempts
        attempts += 1
        current_attempt = attempts
        try:
            if current_attempt == 1:
                raise ProviderUnavailableError(provider="fake")
            yield TextDeltaEvent(text="hello")
            yield DoneEvent(finish_reason="stop")
        finally:
            closed_attempts.append(current_attempt)

    async def fake_sleep(delay_seconds: float) -> None:
        assert closed_attempts == [1]
        slept.append(delay_seconds)

    monkeypatch.setattr(settings, "llm_retry_max_attempts", 2)
    monkeypatch.setattr(settings, "llm_retry_base_delay_seconds", 0.0)
    monkeypatch.setattr(
        "app.services.provider_execution._sleep",
        fake_sleep,
    )

    async def run() -> list[StreamEvent]:
        return [
            event
            async for event in stream_with_provider(
                build_provider(complete, stream),
                build_request(streaming=True),
                limiter=ProviderConcurrencyLimiter(max_active=1, max_waiting=0),
            )
        ]

    events = asyncio.run(run())

    assert events == [
        TextDeltaEvent(text="hello"),
        DoneEvent(finish_reason="stop"),
    ]
    assert attempts == 2
    assert slept == [0.0]
    assert closed_attempts == [1, 2]


def test_stream_does_not_retry_after_first_event(monkeypatch) -> None:
    attempts = 0
    slept: list[float] = []

    async def complete(request: ModelRequest) -> ModelResult:
        return build_result()

    async def stream(request: ModelRequest) -> AsyncIterator[StreamEvent]:
        nonlocal attempts
        attempts += 1
        yield TextDeltaEvent(text="first")
        raise ProviderUnavailableError(provider="fake")

    async def fake_sleep(delay_seconds: float) -> None:
        slept.append(delay_seconds)

    monkeypatch.setattr(settings, "llm_retry_max_attempts", 3)
    monkeypatch.setattr(
        "app.services.provider_execution._sleep",
        fake_sleep,
    )

    async def run() -> None:
        stream_events = stream_with_provider(
            build_provider(complete, stream),
            build_request(streaming=True),
            limiter=ProviderConcurrencyLimiter(max_active=1, max_waiting=0),
        )
        first = await anext(stream_events)
        assert first == TextDeltaEvent(text="first")
        with pytest.raises(ProviderUnavailableError):
            await anext(stream_events)

    asyncio.run(run())

    assert attempts == 1
    assert slept == []


def test_execution_layer_applies_backpressure() -> None:
    async def run() -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def complete(request: ModelRequest) -> ModelResult:
            started.set()
            await release.wait()
            return build_result()

        provider = build_provider(complete)
        limiter = ProviderConcurrencyLimiter(max_active=1, max_waiting=0)
        first = asyncio.create_task(
            complete_with_provider(provider, build_request(), limiter=limiter)
        )
        await asyncio.wait_for(started.wait(), timeout=1.0)

        with pytest.raises(LLMConcurrencyLimitError):
            await complete_with_provider(
                provider,
                build_request(),
                limiter=limiter,
            )

        release.set()
        await first
        assert limiter.snapshot.active == 0
        assert limiter.snapshot.waiting == 0

    asyncio.run(run())


def test_complete_does_not_retry_non_retryable_rate_limit(monkeypatch) -> None:
    attempts = 0
    slept: list[float] = []

    async def complete(request: ModelRequest) -> ModelResult:
        nonlocal attempts
        attempts += 1
        raise ProviderRateLimitError(
            provider="fake",
            retryable=False,
            retry_after_seconds=2.0,
        )

    async def fake_sleep(delay_seconds: float) -> None:
        slept.append(delay_seconds)

    monkeypatch.setattr(settings, "llm_retry_max_attempts", 3)
    monkeypatch.setattr(
        "app.services.provider_execution._sleep",
        fake_sleep,
    )

    with pytest.raises(ProviderRateLimitError) as exc_info:
        asyncio.run(
            complete_with_provider(
                build_provider(complete),
                build_request(),
                limiter=ProviderConcurrencyLimiter(
                    max_active=1,
                    max_waiting=0,
                ),
            )
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.retry_after_seconds is None
    assert attempts == 1
    assert slept == []
