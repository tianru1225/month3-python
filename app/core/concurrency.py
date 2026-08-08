import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.config import settings
from app.services.errors import LLMConcurrencyLimitError


@dataclass(frozen=True)
class ConcurrencySnapshot:
    active: int
    waiting: int
    capacity: int


class ProviderConcurrencyLimiter:
    def __init__(
        self,
        *,
        max_active: int,
        max_waiting: int,
    ) -> None:
        if max_active < 1:
            raise ValueError("max_active must be at least 1")

        if max_waiting < 0:
            raise ValueError("max_waiting must not be negative")

        self.max_active = max_active
        self.max_waiting = max_waiting
        self.capacity = max_active + max_waiting

        self._loop: asyncio.AbstractEventLoop | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._tickets: asyncio.Queue[None] | None = None
        self._active = 0
        self._waiting = 0

    def _ensure_loop(
        self,
    ) -> tuple[
        asyncio.Semaphore,
        asyncio.Queue[None],
    ]:
        loop = asyncio.get_running_loop()

        if self._loop is not loop:
            self._loop = loop
            self._semaphore = asyncio.Semaphore(self.max_active)
            self._tickets = asyncio.Queue(maxsize=self.capacity)
            self._active = 0
            self._waiting = 0

        if self._semaphore is None or self._tickets is None:
            raise RuntimeError("concurrency limiter is not initialized")

        return self._semaphore, self._tickets

    @property
    def snapshot(self) -> ConcurrencySnapshot:
        return ConcurrencySnapshot(
            active=self._active,
            waiting=self._waiting,
            capacity=self.capacity,
        )

    @asynccontextmanager
    async def acquire(
        self,
    ) -> AsyncIterator[None]:
        semaphore, tickets = self._ensure_loop()

        try:
            tickets.put_nowait(None)
        except asyncio.QueueFull as exc:
            raise LLMConcurrencyLimitError("LLM request capacity is full") from exc

        was_waiting = semaphore.locked()
        acquired = False

        if was_waiting:
            self._waiting += 1

        try:
            await semaphore.acquire()
            acquired = True

            if was_waiting:
                self._waiting -= 1

            self._active += 1
            yield
        except BaseException:
            if was_waiting and not acquired:
                self._waiting -= 1
            raise
        finally:
            if acquired:
                self._active -= 1
                semaphore.release()

            tickets.get_nowait()
            tickets.task_done()


_default_limiter: ProviderConcurrencyLimiter | None = None


def get_llm_limiter() -> ProviderConcurrencyLimiter:
    global _default_limiter

    if _default_limiter is None:
        _default_limiter = ProviderConcurrencyLimiter(
            max_active=settings.llm_max_concurrency,
            max_waiting=settings.llm_max_waiting,
        )

    return _default_limiter
