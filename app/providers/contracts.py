from collections.abc import Awaitable, Callable, AsyncIterator
from enum import Enum
from typing import Any, TypeAlias

from pydantic import BaseModel, Field, model_validator

from app.providers.errors import (
    ProviderCapabilityError,
    ProviderContractError,
    ProviderError,
    ProviderExecutionError,
)
from app.schemas.chat import ChatMessage
from app.schemas.llm_stream import (
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    TextDeltaEvent,
    UsageEvent,
)


class Capability(str, Enum):
    CHAT = "chat"
    STREAMING = "streaming"
    STRUCTURED_OUTPUT = "structured_output"
    USAGE = "usage"
    TOOL_CALLING = "tool_calling"


class ModelRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    messages: list[ChatMessage] = Field(min_length=1, max_length=32)
    required_capabilities: frozenset[Capability] = Field(
        default=frozenset({Capability.CHAT})
    )
    response_schema: dict[str, Any] | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1, le=32768)

    @model_validator(mode="after")
    def validate_structured_output_requirement(self) -> "ModelRequest":
        if (
            self.response_schema is not None
            and Capability.STRUCTURED_OUTPUT not in self.required_capabilities
        ):
            raise ValueError(
                "response_schema requires the structured_output capability"
            )
        return self


class ModelUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ModelResult(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    message: ChatMessage
    finish_reason: str | None = None
    usage: ModelUsage | None = None
    structured_output: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_assistant_message(self) -> "ModelResult":
        if self.message.role != "assistant":
            raise ValueError("model result message must use the assistant role")
        return self


CompleteHandler: TypeAlias = Callable[[ModelRequest], Awaitable[ModelResult]]

StreamHandler: TypeAlias = Callable[[ModelRequest], AsyncIterator[StreamEvent]]

_STREAM_EVENT_TYPES = (
    TextDeltaEvent,
    UsageEvent,
    DoneEvent,
    ErrorEvent,
)


class ModelProvider:
    def __init__(
        self,
        *,
        name: str,
        capabilities: frozenset[Capability],
        complete: CompleteHandler,
        stream: StreamHandler | None = None,
    ) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("provider name must not be empty")
        self.name = normalized_name
        self.capabilities = capabilities
        self._complete_handler = complete
        self._stream_handler = stream

    def _require_capabilities(self, request: ModelRequest, *, streaming: bool) -> None:
        required = set(request.required_capabilities)
        if streaming:
            required.add(Capability.STREAMING)
        missing = required.difference(self.capabilities)
        if missing:
            raise ProviderCapabilityError(
                provider=self.name,
                missing_capabilities=(capability.value for capability in missing),
            )

    async def complete(self, request: ModelRequest) -> ModelResult:
        self._require_capabilities(request, streaming=False)
        try:
            result = await self._complete_handler(request)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderExecutionError(provider=self.name) from exc
        if not isinstance(result, ModelResult):
            raise ProviderContractError(
                "provider completion returned an invalid result type",
                provider=self.name,
            )
        if result.provider != self.name:
            raise ProviderContractError(
                "provider result identity does not match provider name",
                provider=self.name,
            )
        return result

    def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[StreamEvent]:
        self._require_capabilities(request, streaming=True)
        if self._stream_handler is None:
            raise ProviderContractError(
                "streaming capability has no stream handler", provider=self.name
            )
        return self._iterate_stream(request, self._stream_handler)

    async def _iterate_stream(
        self,
        request: ModelRequest,
        handler: StreamHandler,
    ) -> AsyncIterator[StreamEvent]:
        terminal_seen = False
        try:
            async for event in handler(request):
                if terminal_seen:
                    raise ProviderContractError(
                        "provider emitted an event after a terminal event",
                        provider=self.name,
                    )
                if not isinstance(event, _STREAM_EVENT_TYPES):
                    raise ProviderContractError(
                        "provider emitted an invalid stream event", provider=self.name
                    )
                yield event

                if isinstance(event, (DoneEvent, ErrorEvent)):
                    terminal_seen = True
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderExecutionError(provider=self.name) from exc
        if not terminal_seen:
            raise ProviderContractError(
                "provider stream ended without a terminal event",
                provider=self.name,
            )
