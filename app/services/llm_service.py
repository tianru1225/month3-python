from collections.abc import AsyncGenerator
from contextlib import aclosing
import httpx

from app.config import settings
from app.core.concurrency import ProviderConcurrencyLimiter
from app.providers import (
    Capability,
    ModelRequest,
    ProviderAuthenticationError,
    ProviderError,
    ProviderGenerationTimeoutError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.qwen_adapter import QwenAdapter
from app.schemas.chat import ChatMessage, ChatResult
from app.schemas.llm_stream import StreamEvent
from app.services.errors import (
    LLMGenerationTimeoutError,
    LLMRateLimitError,
    LLMRequestTimeoutError,
    LLMUpstreamConnectionError,
    LLMUpstreamError,
)
from app.services.provider_execution import (
    complete_with_provider,
    stream_with_provider,
)


def _build_request(messages: list[ChatMessage], *, streaming: bool) -> ModelRequest:
    capabilities = {Capability.CHAT, Capability.USAGE}
    if streaming:
        capabilities.add(Capability.STREAMING)
    return ModelRequest(
        model=settings.qwen_model,
        messages=messages,
        required_capabilities=frozenset(capabilities),
        max_output_tokens=settings.qwen_max_output_tokens,
    )


def _translate_provider_error(error: ProviderError) -> LLMUpstreamError:
    if isinstance(error, ProviderRateLimitError):
        return LLMRateLimitError("Qwen rate limited request")
    if isinstance(error, ProviderTimeoutError):
        return LLMRequestTimeoutError("Qwen request timed out")
    if isinstance(error, ProviderGenerationTimeoutError):
        return LLMGenerationTimeoutError("Qwen generation timed out")
    if isinstance(error, ProviderUnavailableError):
        return LLMUpstreamConnectionError("Qwen is unavailable")
    if isinstance(error, ProviderAuthenticationError):
        return LLMUpstreamError("Qwen authentication failed")
    return LLMUpstreamError("Qwen request failed")


async def _chat_with_client(
    messages: list[ChatMessage],
    *,
    client: httpx.AsyncClient,
    limiter: ProviderConcurrencyLimiter | None,
) -> ChatResult:
    try:
        provider = QwenAdapter(client=client).provider
        result = await complete_with_provider(
            provider, _build_request(messages, streaming=False), limiter=limiter
        )
    except ProviderError as exc:
        raise _translate_provider_error(exc) from exc
    except ValueError as exc:
        raise LLMUpstreamError("Qwen configuration is invalid") from exc
    return ChatResult(
        model=result.model, message=result.message, finish_reason=result.finish_reason
    )


async def chat_with_llm(
    messages: list[ChatMessage],
    *,
    client: httpx.AsyncClient | None = None,
    limiter: ProviderConcurrencyLimiter | None = None,
) -> ChatResult:
    if client is not None:
        return await _chat_with_client(
            messages,
            client=client,
            limiter=limiter,
        )
    async with httpx.AsyncClient() as owned_client:
        return await _chat_with_client(messages, client=owned_client, limiter=limiter)


async def _stream_with_client(
    messages: list[ChatMessage],
    *,
    client: httpx.AsyncClient,
    limiter: ProviderConcurrencyLimiter | None,
) -> AsyncGenerator[StreamEvent, None]:
    try:
        provider = QwenAdapter(client=client).provider
        async with aclosing(
            stream_with_provider(
                provider, _build_request(messages, streaming=True), limiter=limiter
            )
        ) as stream:
            async for event in stream:
                yield event
    except ProviderError as exc:
        raise _translate_provider_error(exc) from exc
    except ValueError as exc:
        raise LLMUpstreamError("Qwen configuration is invalid") from exc


async def stream_chat_with_llm(
    messages: list[ChatMessage],
    *,
    client: httpx.AsyncClient | None = None,
    limiter: ProviderConcurrencyLimiter | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    if client is not None:
        async with aclosing(
            _stream_with_client(messages, client=client, limiter=limiter)
        ) as stream:
            async for event in stream:
                yield event
        return

    async with httpx.AsyncClient() as owned_client:
        async with aclosing(
            _stream_with_client(
                messages,
                client=owned_client,
                limiter=limiter,
            )
        ) as stream:
            async for event in stream:
                yield event
