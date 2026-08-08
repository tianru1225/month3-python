import asyncio
from typing import Any

import httpx
import pytest

from app.config import settings
from app.core.concurrency import (
    ProviderConcurrencyLimiter,
)
from app.schemas.chat import ChatMessage, ChatResult
from app.services.errors import (
    LLMConcurrencyLimitError,
)
from app.services.llm_service import chat_with_llm


def _messages() -> list[ChatMessage]:
    return [
        ChatMessage(
            role="user",
            content="hello",
        )
    ]


def _success_json() -> dict[str, Any]:
    return {
        "model": "qwen2.5:3b",
        "message": {
            "role": "assistant",
            "content": "CONCURRENCY_OK",
        },
        "done": True,
        "done_reason": "stop",
    }


async def _wait_until(
    predicate,
) -> None:
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0)

    raise AssertionError("condition was not reached")


def test_queue_capacity_rejects_excess_requests() -> None:
    async def run() -> None:
        limiter = ProviderConcurrencyLimiter(
            max_active=1,
            max_waiting=1,
        )
        release = asyncio.Event()
        waiting_started = asyncio.Event()

        async def active_task() -> None:
            async with limiter.acquire():
                await release.wait()

        async def waiting_task() -> None:
            async with limiter.acquire():
                waiting_started.set()

        first = asyncio.create_task(active_task())
        await _wait_until(lambda: limiter.snapshot.active == 1)

        second = asyncio.create_task(waiting_task())
        await _wait_until(lambda: limiter.snapshot.waiting == 1)

        with pytest.raises(LLMConcurrencyLimitError) as exc_info:
            async with limiter.acquire():
                raise AssertionError("capacity should reject")

        assert exc_info.value.http_status == 429
        assert limiter.snapshot.active == 1
        assert limiter.snapshot.waiting == 1

        release.set()
        await asyncio.wait_for(
            waiting_started.wait(),
            timeout=1.0,
        )
        await second
        await first

        assert limiter.snapshot.active == 0
        assert limiter.snapshot.waiting == 0

    asyncio.run(run())


def test_service_limits_active_provider_calls(
    monkeypatch,
) -> None:
    async def run() -> None:
        limiter = ProviderConcurrencyLimiter(
            max_active=2,
            max_waiting=3,
        )
        active = 0
        max_seen = 0

        async def handler(
            request: httpx.Request,
        ) -> httpx.Response:
            nonlocal active, max_seen
            active += 1
            max_seen = max(max_seen, active)

            await asyncio.sleep(0.01)

            active -= 1
            return httpx.Response(
                200,
                json=_success_json(),
            )

        monkeypatch.setattr(
            settings,
            "llm_retry_max_attempts",
            1,
        )

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            results = await asyncio.gather(
                *(
                    chat_with_llm(
                        _messages(),
                        client=client,
                        limiter=limiter,
                    )
                    for _ in range(5)
                )
            )

        assert len(results) == 5
        assert all(isinstance(result, ChatResult) for result in results)
        assert max_seen == 2
        assert active == 0
        assert limiter.snapshot.active == 0
        assert limiter.snapshot.waiting == 0

    asyncio.run(run())


def test_service_releases_permit_after_upstream_error(
    monkeypatch,
) -> None:
    request_count = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        if request_count == 1:
            raise httpx.ConnectError(
                "upstream unavailable",
                request=request,
            )

        return httpx.Response(
            200,
            json=_success_json(),
        )

    async def run() -> None:
        limiter = ProviderConcurrencyLimiter(
            max_active=1,
            max_waiting=0,
        )

        monkeypatch.setattr(
            settings,
            "llm_retry_max_attempts",
            1,
        )

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as client:
            with pytest.raises(Exception):
                await chat_with_llm(
                    _messages(),
                    client=client,
                    limiter=limiter,
                )

            result = await chat_with_llm(
                _messages(),
                client=client,
                limiter=limiter,
            )

        assert result.message.content == ("CONCURRENCY_OK")
        assert request_count == 2
        assert limiter.snapshot.active == 0
        assert limiter.snapshot.waiting == 0

    asyncio.run(run())
