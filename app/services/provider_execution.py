import asyncio
import logging
import random
from collections.abc import AsyncGenerator
from contextlib import aclosing

from app.config import settings
from app.core.concurrency import ProviderConcurrencyLimiter, get_llm_limiter
from app.providers import ModelProvider, ModelRequest, ModelResult, ProviderError
from app.schemas.llm_stream import StreamEvent


logger = logging.getLogger("app.provider_execution")


async def _sleep(delay_seconds: float) -> None:
    await asyncio.sleep(delay_seconds)


def _has_attempt_remaining(attempt_index: int) -> bool:
    return attempt_index + 1 < settings.llm_retry_max_attempts


def _calculate_retry_delay(
    error: ProviderError,
    attempt_index: int,
) -> float | None:
    max_delay = settings.llm_retry_max_delay_seconds

    if error.retry_after_seconds is not None:
        if error.retry_after_seconds > max_delay:
            return None
        return error.retry_after_seconds

    exponential_cap = min(
        max_delay,
        settings.llm_retry_base_delay_seconds * (2**attempt_index),
    )
    return random.uniform(0.0, exponential_cap)


async def _wait_before_retry(
    error: ProviderError,
    *,
    attempt_index: int,
) -> None:
    delay_seconds = _calculate_retry_delay(error, attempt_index)

    if delay_seconds is None:
        raise error

    logger.warning(
        "retrying model provider provider=%s next_attempt=%s/%s "
        "delay_seconds=%.3f code=%s",
        error.provider,
        attempt_index + 2,
        settings.llm_retry_max_attempts,
        delay_seconds,
        error.code,
    )

    await _sleep(delay_seconds)


async def complete_with_provider(
    provider: ModelProvider,
    request: ModelRequest,
    *,
    limiter: ProviderConcurrencyLimiter | None = None,
) -> ModelResult:
    active_limiter = limiter if limiter is not None else get_llm_limiter()

    async with active_limiter.acquire():
        for attempt_index in range(settings.llm_retry_max_attempts):
            try:
                return await provider.complete(request)
            except ProviderError as exc:
                if not exc.retryable or not _has_attempt_remaining(attempt_index):
                    raise

                await _wait_before_retry(
                    exc,
                    attempt_index=attempt_index,
                )

    raise RuntimeError("provider completion retry loop exhausted")


async def stream_with_provider(
    provider: ModelProvider,
    request: ModelRequest,
    *,
    limiter: ProviderConcurrencyLimiter | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    active_limiter = limiter if limiter is not None else get_llm_limiter()

    async with active_limiter.acquire():
        for attempt_index in range(settings.llm_retry_max_attempts):
            emitted_event = False

            try:
                async with aclosing(provider.stream(request)) as stream:
                    async for event in stream:
                        emitted_event = True
                        yield event
                return

            except ProviderError as exc:
                if (
                    emitted_event
                    or not exc.retryable
                    or not _has_attempt_remaining(attempt_index)
                ):
                    raise

                await _wait_before_retry(
                    exc,
                    attempt_index=attempt_index,
                )

    raise RuntimeError("provider stream retry loop exhausted")
