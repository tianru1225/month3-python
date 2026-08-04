import asyncio
import logging
from collections.abc import AsyncIterator

import httpx
import pytest

from app.routers.chat import _stream_as_ndjson
from app.schemas.chat import ChatMessage
from app.schemas.llm_stream import StreamEvent, TextDeltaEvent
from app.services.llm_service import stream_chat_with_llm


class BlockingNDJSONStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.waiting = asyncio.Event()
        self.closed = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield (b'{"message":{"content":"first"},"done":false}\n')

        self.waiting.set()
        never = asyncio.Event()
        await never.wait()

    async def aclose(self) -> None:
        self.closed.set()


def test_cancelling_consumer_closes_upstream_response() -> None:
    async def run() -> None:
        body = BlockingNDJSONStream()

        def handler(
            request: httpx.Request,
        ) -> httpx.Response:
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/x-ndjson",
                },
                stream=body,
            )

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport,
        ) as injected:
            iterator = stream_chat_with_llm(
                [
                    ChatMessage(
                        role="user",
                        content="hello",
                    )
                ],
                client=injected,
            )

            first = await anext(iterator)
            assert first == TextDeltaEvent(text="first")

            read_task = asyncio.create_task(
                anext(iterator),
                name="day100-upstream-read",
            )

            await asyncio.wait_for(
                body.waiting.wait(),
                timeout=1.0,
            )

            read_task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await read_task

            await iterator.aclose()

            await asyncio.wait_for(
                body.closed.wait(),
                timeout=1.0,
            )

            assert read_task.done()
            assert not any(
                task.get_name() == "day100-upstream-read"
                for task in asyncio.all_tasks()
            )

    asyncio.run(run())


def test_closing_route_stream_closes_service_generator(
    monkeypatch,
    caplog,
) -> None:
    async def run() -> None:
        upstream_closed = asyncio.Event()

        async def fake_stream(
            messages: list[ChatMessage],
        ) -> AsyncIterator[StreamEvent]:
            assert messages

            try:
                yield TextDeltaEvent(text="first")
                never = asyncio.Event()
                await never.wait()
            finally:
                upstream_closed.set()

        monkeypatch.setattr(
            "app.routers.chat.stream_chat_with_llm",
            fake_stream,
        )

        iterator = _stream_as_ndjson(
            [
                ChatMessage(
                    role="user",
                    content="hello",
                )
            ],
            request_id="day100-test",
        )

        first = await anext(iterator)
        assert '"type":"text_delta"' in first

        await iterator.aclose()

        await asyncio.wait_for(
            upstream_closed.wait(),
            timeout=1.0,
        )

    with caplog.at_level(
        logging.INFO,
        logger="app.chat_stream",
    ):
        asyncio.run(run())

    assert "request_id=day100-test outcome=cancelled" in caplog.text
