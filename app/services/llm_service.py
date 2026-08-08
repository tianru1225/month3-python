import asyncio
import json
import logging
import math
import random
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.core.concurrency import ProviderConcurrencyLimiter, get_llm_limiter
from app.schemas.llm_stream import DoneEvent, ErrorEvent, StreamEvent
from app.schemas.chat import ChatMessage, ChatResult
from app.services.errors import (
    LLMGenerationTimeoutError,
    LLMRequestTimeoutError,
    LLMUpstreamConnectionError,
    LLMUpstreamError,
    LLMRateLimitError,
)
from app.services.ollama_stream import parse_ollama_stream_line

logger = logging.getLogger("app.llm_stream")

_RETRYABLE_STATUS_CODES = frozenset(
    {
        429,
        502,
        503,
        504,
    }
)


class _OllamaChatResponse(BaseModel):
    model: str
    message: ChatMessage
    done_reason: str | None = None


def _build_ollama_payload(
    messages: list[ChatMessage], *, stream: bool
) -> dict[str, object]:
    return {
        "model": settings.ollama_model,
        "messages": [message.model_dump() for message in messages],
        "stream": stream,
        "options": {
            "num_ctx": settings.ollama_num_ctx,
            "num_predict": settings.ollama_num_predict,
        },
    }


def _build_ollama_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.ollama_connect_timeout_seconds,
        read=settings.ollama_read_timeout_seconds,
        write=settings.ollama_write_timeout_seconds,
        pool=settings.ollama_pool_timeout_seconds,
    )


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        seconds = float(normalized)
    except ValueError:
        seconds = -1.0
    if math.isfinite(seconds) and seconds >= 0:
        return seconds
    try:
        retry_at = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max(
        0.0,
        (retry_at - now).total_seconds(),
    )


def _calculate_retry_delay(
    attempt_index: int, *, response: httpx.Response | None = None
) -> float | None:
    max_delay = settings.llm_retry_max_delay_seconds
    if response is not None:
        header = response.headers.get("Retry-After")
        retry_after = _parse_retry_after(header)

        if retry_after is not None:
            if retry_after > max_delay:
                return None
            return retry_after
    exponential_cap = min(
        max_delay,
        settings.llm_retry_base_delay_seconds * (2**attempt_index),
    )
    return random.uniform(0.0, exponential_cap)


def _has_attempt_remaining(attempt_index: int) -> bool:
    return attempt_index + 1 < settings.llm_retry_max_attempts


def _is_retryable_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_STATUS_CODES


def _is_retryable_transport_error(exc: httpx.HTTPError) -> bool:
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.PoolTimeout,
        ),
    )


async def _sleep(delay_seconds: float) -> None:
    await asyncio.sleep(delay_seconds)


async def _wait_before_retry(
    delay_seconds: float,
    *,
    attempt_index: int,
    reason: str,
) -> None:
    logger.warning(
        "retrying LLM upstream next_attempt=%s/%s delay_seconds=%.3f reason=%s",
        attempt_index + 2,
        settings.llm_retry_max_attempts,
        delay_seconds,
        reason,
    )
    await _sleep(delay_seconds)


def _translate_httpx_error(exc: httpx.HTTPError) -> LLMUpstreamError:
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 429:
            return LLMRateLimitError("LLM upstream rate limited request")
        return LLMUpstreamError("LLM upstream returned an error status")
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError)):
        return LLMUpstreamConnectionError("LLM upstream connection failed")
    if isinstance(exc, httpx.ReadTimeout):
        return LLMGenerationTimeoutError("LLM upstream read timed out")
    if isinstance(exc, (httpx.WriteTimeout, httpx.PoolTimeout)):
        return LLMRequestTimeoutError("LLM upstream request timed out")
    if isinstance(exc, httpx.TimeoutException):
        return LLMRequestTimeoutError("LLM upstream request timed out")
    return LLMUpstreamError("LLM upstream request failed")


async def _chat_with_client(
    messages: list[ChatMessage], *, client: httpx.AsyncClient
) -> ChatResult:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    for attempt_index in range(settings.llm_retry_max_attempts):
        try:
            response = await client.post(
                url,
                json=_build_ollama_payload(messages, stream=False),
                timeout=_build_ollama_timeout(),
            )
            if _is_retryable_status(response.status_code) and _has_attempt_remaining(
                attempt_index
            ):
                retry_delay = _calculate_retry_delay(
                    attempt_index,
                    response=response,
                )
                if retry_delay is not None:
                    await _wait_before_retry(
                        retry_delay,
                        attempt_index=attempt_index,
                        reason=f"status={response.status_code}",
                    )
                    continue
            response.raise_for_status()
            upstream = _OllamaChatResponse.model_validate(response.json())
            return ChatResult(
                model=upstream.model,
                message=upstream.message,
                finish_reason=upstream.done_reason,
            )
        except httpx.HTTPError as exc:
            if _is_retryable_transport_error(exc) and _has_attempt_remaining(
                attempt_index
            ):
                retry_delay = _calculate_retry_delay(attempt_index)
                if retry_delay is not None:
                    await _wait_before_retry(
                        retry_delay,
                        attempt_index=attempt_index,
                        reason=type(exc).__name__,
                    )
                    continue
            raise _translate_httpx_error(exc) from exc
        except (
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise LLMUpstreamError("LLM upstream response is invalid") from exc
    raise LLMUpstreamError("LLM upstream retry loop exhausted")


async def chat_with_llm(
    messages: list[ChatMessage],
    *,
    client: httpx.AsyncClient | None = None,
    limiter: ProviderConcurrencyLimiter | None = None,
) -> ChatResult:
    active_limiter = limiter if limiter is not None else get_llm_limiter()
    async with active_limiter.acquire():
        if client is not None:
            return await _chat_with_client(messages, client=client)
        async with httpx.AsyncClient() as owned_client:
            return await _chat_with_client(messages, client=owned_client)


async def _stream_chat_with_client(
    messages: list[ChatMessage],
    *,
    client: httpx.AsyncClient,
) -> AsyncGenerator[StreamEvent, None]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    for attempt_index in range(settings.llm_retry_max_attempts):
        emitted_event = False

        try:
            retry_delay: float | None = None
            retry_reason: str | None = None

            async with client.stream(
                "POST",
                url,
                json=_build_ollama_payload(messages, stream=True),
                timeout=_build_ollama_timeout(),
            ) as response:
                if _is_retryable_status(
                    response.status_code
                ) and _has_attempt_remaining(attempt_index):
                    retry_delay = _calculate_retry_delay(
                        attempt_index,
                        response=response,
                    )

                    if retry_delay is not None:
                        retry_reason = f"status={response.status_code}"

                if retry_delay is None:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        events = parse_ollama_stream_line(line)

                        for event in events:
                            emitted_event = True
                            yield event

                        if any(
                            isinstance(event, (DoneEvent, ErrorEvent))
                            for event in events
                        ):
                            return

                    return

            # Response 已退出上下文并释放连接池槽位。
            if retry_delay is not None:
                await _wait_before_retry(
                    retry_delay,
                    attempt_index=attempt_index,
                    reason=retry_reason or "retryable_status",
                )
                continue
        except asyncio.CancelledError:
            logger.info("LLM upstream stream cancelled")
            raise
        except httpx.HTTPError as exc:
            if (
                not emitted_event
                and _is_retryable_transport_error(exc)
                and _has_attempt_remaining(attempt_index)
            ):
                retry_delay = _calculate_retry_delay(attempt_index)

                if retry_delay is not None:
                    try:
                        await _wait_before_retry(
                            retry_delay,
                            attempt_index=attempt_index,
                            reason=type(exc).__name__,
                        )
                    except asyncio.CancelledError:
                        logger.info("LLM upstream stream cancelled")
                        raise

                    continue

            raise _translate_httpx_error(exc) from exc

    raise LLMUpstreamError("LLM upstream retry loop exhausted")


async def stream_chat_with_llm(
    messages: list[ChatMessage],
    *,
    client: httpx.AsyncClient | None = None,
    limiter: ProviderConcurrencyLimiter | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    active_limiter = limiter if limiter is not None else get_llm_limiter()
    async with active_limiter.acquire():
        if client is not None:
            async for event in _stream_chat_with_client(messages, client=client):
                yield event
            return
        async with httpx.AsyncClient() as owned_client:
            async for event in _stream_chat_with_client(messages, client=owned_client):
                yield event
