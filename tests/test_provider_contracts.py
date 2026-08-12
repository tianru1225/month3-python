import asyncio
from collections.abc import AsyncIterator

import pytest

from app.providers import (
    Capability,
    ModelProvider,
    ModelRequest,
    ModelResult,
    ModelUsage,
    ProviderCapabilityError,
    ProviderExecutionError,
)
from app.schemas.chat import ChatMessage
from app.schemas.llm_stream import (
    DoneEvent,
    StreamEvent,
    TextDeltaEvent,
    UsageEvent,
)


def model_request(
    *capabilities: Capability,
) -> ModelRequest:
    required = capabilities or (Capability.CHAT,)

    return ModelRequest(
        model="fake-model",
        messages=[
            ChatMessage(
                role="user",
                content="Explain provider boundaries",
            )
        ],
        required_capabilities=frozenset(required),
        max_output_tokens=200,
    )


def test_complete_returns_vendor_neutral_result() -> None:
    async def complete(
        request: ModelRequest,
    ) -> ModelResult:
        assert request.model == "fake-model"

        return ModelResult(
            provider="fake",
            model=request.model,
            message=ChatMessage(
                role="assistant",
                content="A provider boundary hides vendor details.",
            ),
            finish_reason="stop",
            usage=ModelUsage(
                input_tokens=10,
                output_tokens=8,
                cached_input_tokens=2,
            ),
        )

    provider = ModelProvider(
        name="fake",
        capabilities=frozenset(
            {
                Capability.CHAT,
                Capability.USAGE,
            }
        ),
        complete=complete,
    )

    result = asyncio.run(
        provider.complete(
            model_request(
                Capability.CHAT,
                Capability.USAGE,
            )
        )
    )

    assert result.provider == "fake"
    assert result.message.role == "assistant"
    assert result.usage is not None
    assert result.usage.total_tokens == 18


def test_stream_uses_shared_terminal_event_contract() -> None:
    async def complete(
        request: ModelRequest,
    ) -> ModelResult:
        return ModelResult(
            provider="fake",
            model=request.model,
            message=ChatMessage(
                role="assistant",
                content="unused",
            ),
        )

    async def stream(
        request: ModelRequest,
    ) -> AsyncIterator[StreamEvent]:
        assert request.model == "fake-model"
        yield TextDeltaEvent(text="hello")
        yield UsageEvent(
            input_tokens=4,
            output_tokens=1,
        )
        yield DoneEvent(finish_reason="stop")

    provider = ModelProvider(
        name="fake",
        capabilities=frozenset(
            {
                Capability.CHAT,
                Capability.STREAMING,
                Capability.USAGE,
            }
        ),
        complete=complete,
        stream=stream,
    )

    async def collect() -> list[StreamEvent]:
        return [
            event
            async for event in provider.stream(
                model_request(
                    Capability.CHAT,
                    Capability.STREAMING,
                )
            )
        ]

    events = asyncio.run(collect())

    assert [event.type for event in events] == [
        "text_delta",
        "usage",
        "done",
    ]


def test_missing_capability_is_rejected_before_execution() -> None:
    complete_called = False

    async def complete(
        request: ModelRequest,
    ) -> ModelResult:
        nonlocal complete_called
        complete_called = True

        return ModelResult(
            provider="fake",
            model=request.model,
            message=ChatMessage(
                role="assistant",
                content="unexpected",
            ),
        )

    provider = ModelProvider(
        name="fake",
        capabilities=frozenset({Capability.CHAT}),
        complete=complete,
    )

    request = ModelRequest(
        model="fake-model",
        messages=[
            ChatMessage(
                role="user",
                content="Return structured output",
            )
        ],
        required_capabilities=frozenset(
            {
                Capability.CHAT,
                Capability.STRUCTURED_OUTPUT,
            }
        ),
        response_schema={
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                }
            },
        },
    )

    with pytest.raises(ProviderCapabilityError) as exc_info:
        asyncio.run(provider.complete(request))

    assert complete_called is False
    assert exc_info.value.provider == "fake"
    assert exc_info.value.missing_capabilities == ("structured_output",)


def test_vendor_sdk_errors_do_not_cross_provider_boundary() -> None:
    class FakeVendorSDKError(Exception):
        pass

    async def complete(
        request: ModelRequest,
    ) -> ModelResult:
        raise FakeVendorSDKError("vendor-token=secret-completion")

    async def stream(
        request: ModelRequest,
    ) -> AsyncIterator[StreamEvent]:
        for _message in request.messages:
            raise FakeVendorSDKError("vendor-token=secret-stream")

        yield DoneEvent(finish_reason="stop")

    provider = ModelProvider(
        name="fake",
        capabilities=frozenset(
            {
                Capability.CHAT,
                Capability.STREAMING,
            }
        ),
        complete=complete,
        stream=stream,
    )

    async def run() -> tuple[
        ProviderExecutionError,
        ProviderExecutionError,
    ]:
        with pytest.raises(ProviderExecutionError) as complete_info:
            await provider.complete(model_request())

        with pytest.raises(ProviderExecutionError) as stream_info:
            async for _event in provider.stream(
                model_request(
                    Capability.CHAT,
                    Capability.STREAMING,
                )
            ):
                raise AssertionError("broken stream must not emit events")

        return (
            complete_info.value,
            stream_info.value,
        )

    complete_error, stream_error = asyncio.run(run())

    assert complete_error.provider == "fake"
    assert stream_error.provider == "fake"
    assert "secret" not in str(complete_error)
    assert "secret" not in str(stream_error)
    assert isinstance(
        complete_error.__cause__,
        FakeVendorSDKError,
    )
    assert isinstance(
        stream_error.__cause__,
        FakeVendorSDKError,
    )
