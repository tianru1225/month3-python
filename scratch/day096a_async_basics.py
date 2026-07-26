import asyncio
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TimingResult:
    sync_sequential_seconds: float
    async_sequential_seconds: float
    async_gather_seconds: float
    blocking_gather_seconds: float


def sync_wait(label: str, delay: float) -> str:
    time.sleep(delay)
    return label


async def async_wait(label: str, delay: float) -> str:
    await asyncio.sleep(delay)
    return label


async def blocking_wait(label: str, delay: float) -> str:
    time.sleep(delay)
    return label


async def measure_async_waits(
    labels: list[str],
    delay: float,
) -> tuple[float, float, float]:
    start = time.perf_counter()
    sequential_results = []

    for label in labels:
        result = await async_wait(label, delay)
        sequential_results.append(result)

    async_sequential_seconds = time.perf_counter() - start
    assert sequential_results == labels

    start = time.perf_counter()
    gather_results = await asyncio.gather(
        *(async_wait(label, delay) for label in labels)
    )
    async_gather_seconds = time.perf_counter() - start
    assert gather_results == labels

    start = time.perf_counter()
    blocking_results = await asyncio.gather(
        *(blocking_wait(label, delay) for label in labels)
    )
    blocking_gather_seconds = time.perf_counter() - start
    assert blocking_results == labels

    return (
        async_sequential_seconds,
        async_gather_seconds,
        blocking_gather_seconds,
    )


def run_experiment(task_count: int = 3, delay: float = 0.25) -> TimingResult:
    labels = [f"task-{index}" for index in range(1, task_count + 1)]
    start = time.perf_counter()
    sync_results = [sync_wait(label, delay) for label in labels]
    sync_sequential_seconds = time.perf_counter() - start
    assert sync_results == labels
    (
        async_sequential_seconds,
        async_gather_seconds,
        blocking_gather_seconds,
    ) = asyncio.run(measure_async_waits(labels, delay))

    return TimingResult(
        sync_sequential_seconds=sync_sequential_seconds,
        async_sequential_seconds=async_sequential_seconds,
        async_gather_seconds=async_gather_seconds,
        blocking_gather_seconds=blocking_gather_seconds,
    )


def main() -> None:
    result = run_experiment()
    print(
        "sync_sequential_s:",
        round(result.sync_sequential_seconds, 3),
    )
    print(
        "async_sequential_s:",
        round(result.async_sequential_seconds, 3),
    )
    print(
        "async_gather_s:",
        round(result.async_gather_seconds, 3),
    )
    print(
        "blocking_gather_s:",
        round(result.blocking_gather_seconds, 3),
    )
    speedup = result.async_sequential_seconds / result.async_gather_seconds
    print("gather_speedup:", round(speedup, 2))
    assert result.async_gather_seconds < result.async_sequential_seconds * 0.7
    assert result.blocking_gather_seconds > result.async_gather_seconds * 2


if __name__ == "__main__":
    main()
