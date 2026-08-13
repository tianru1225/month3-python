import asyncio
from collections.abc import AsyncIterator

import pytest

from app.providers import (
    Capability,
    ModelRequest,
    ModelResult,
    ProviderCapabilityError,
)
from app.providers.ollama_adapter import OllamaAdapter
from app.schemas.chat import ChatMessage, ChatResult
from app.schemas.llm_stream import (
    DoneEvent,
    StreamEvent,
    TextDeltaEvent,
)


def build_request(
    *capabilities: Capability,
) -> ModelRequest:
    required = capabilities or (Capability.CHAT,)

    return ModelRequest(
        model="qwen2.5:3b",
        messages=[
            ChatMessage(
                role="user",
                content="Explain Ollama adapter boundaries",
            )
        ],
        required_capabilities=frozenset(required),
    )


def test_adapter_maps_legacy_chat_result_to_model_result() -> None:
    received_messages: list[ChatMessage] = []

    async def complete(
        messages: list[ChatMessage],
    ) -> ChatResult:
        received_messages.extend(messages)

        return ChatResult(
            model="qwen2.5:3b",
            message=ChatMessage(
                role="assistant",
                content="The adapter hides the legacy service shape.",
            ),
            finish_reason="stop",
        )

    async def stream(
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        yield DoneEvent(finish_reason="stop")

    adapter = OllamaAdapter(
        complete=complete,
        stream=stream,
    )

    async def run() -> ModelResult:
        return await adapter.provider.complete(
            build_request(
                Capability.CHAT,
            )
        )

    result = asyncio.run(run())

    assert result.provider == "ollama"
    assert result.model == "qwen2.5:3b"
    assert result.message.role == "assistant"
    assert result.message.content == ("The adapter hides the legacy service shape.")
    assert received_messages[0].content == ("Explain Ollama adapter boundaries")


def test_adapter_reuses_existing_stream_events() -> None:
    async def complete(
        messages: list[ChatMessage],
    ) -> ChatResult:
        return ChatResult(
            model="qwen2.5:3b",
            message=ChatMessage(
                role="assistant",
                content="unused",
            ),
        )

    async def stream(
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        assert messages
        yield TextDeltaEvent(text="hello")
        yield DoneEvent(finish_reason="stop")

    adapter = OllamaAdapter(
        complete=complete,
        stream=stream,
    )

    async def collect() -> list[StreamEvent]:
        return [
            event
            async for event in adapter.provider.stream(
                build_request(
                    Capability.CHAT,
                    Capability.STREAMING,
                )
            )
        ]

    events = asyncio.run(collect())

    assert events == [
        TextDeltaEvent(text="hello"),
        DoneEvent(finish_reason="stop"),
    ]


def test_adapter_rejects_unsupported_structured_output_before_handler() -> None:
    complete_called = False

    async def complete(
        messages: list[ChatMessage],
    ) -> ChatResult:
        nonlocal complete_called
        complete_called = True

        return ChatResult(
            model="qwen2.5:3b",
            message=ChatMessage(
                role="assistant",
                content="unexpected",
            ),
        )

    async def stream(
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        yield DoneEvent(finish_reason="stop")

    adapter = OllamaAdapter(
        complete=complete,
        stream=stream,
    )

    request = ModelRequest(
        model="qwen2.5:3b",
        messages=[
            ChatMessage(
                role="user",
                content="Return a structured plan",
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
                "title": {
                    "type": "string",
                }
            },
        },
    )

    with pytest.raises(ProviderCapabilityError) as exc_info:
        asyncio.run(adapter.provider.complete(request))

    assert complete_called is False
    assert exc_info.value.provider == "ollama"
    assert exc_info.value.missing_capabilities == ("structured_output",)
