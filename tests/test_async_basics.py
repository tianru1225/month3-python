import asyncio

from scratch.day096a_async_basics import async_wait, run_experiment


def test_async_wait_returns_result() -> None:
    result = asyncio.run(async_wait("day096a", 0.01))
    assert result == "day096a"


def test_gather_is_faster_than_sequential_waiting() -> None:
    result = run_experiment(
        task_count=3,
        delay=0.03,
    )

    assert result.async_gather_seconds < result.async_sequential_seconds * 0.7
    assert result.blocking_gather_seconds > result.async_gather_seconds * 2
