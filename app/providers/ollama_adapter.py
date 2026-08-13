from collections.abc import AsyncIterator, Awaitable, Callable

from app.providers.contracts import (
    Capability,
    ModelProvider,
    ModelRequest,
    ModelResult,
)
from app.schemas.chat import ChatMessage, ChatResult
from app.schemas.llm_stream import StreamEvent

LegacyCompleteHandler = Callable[
    [list[ChatMessage]],
    Awaitable[ChatResult],
]

LegacyStreamHandler = Callable[[list[ChatMessage]], AsyncIterator[StreamEvent]]


class OllamaAdapter:
    """Wraps the existing Ollama service functions in the Provider contract."""

    def __init__(
        self,
        *,
        complete: LegacyCompleteHandler,
        stream: LegacyStreamHandler,
    ) -> None:
        self._complete_handler = complete
        self._stream_handler = stream
        self._provider = ModelProvider(
            name="ollama",
            capabilities=frozenset({Capability.CHAT, Capability.STREAMING}),
            complete=self._complete,
            stream=self._stream,
        )

    @property
    def provider(self) -> ModelProvider:
        return self._provider

    async def _complete(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        result = await self._complete_handler(request.messages)
        return ModelResult(
            provider="ollama",
            model=result.model,
            message=result.message,
            finish_reason=result.finish_reason,
        )

    def _stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[StreamEvent]:
        return self._stream_handler(request.messages)
