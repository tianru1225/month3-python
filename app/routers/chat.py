import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.deps.auth import verify_api_key
from app.schemas.chat import ChatMessage, ChatRequest, ChatResult
from app.schemas.llm_stream import DoneEvent, ErrorEvent
from app.schemas.response import ApiResponse
from app.services.errors import LLMUpstreamError
from app.services.llm_service import chat_with_llm, stream_chat_with_llm
from app.utils.response import ok

logger = logging.getLogger("app.chat_stream")

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post(
    "/chat",
    response_model=ApiResponse[ChatResult],
    dependencies=[Depends(verify_api_key)],
)
async def create_chat(payload: ChatRequest) -> ApiResponse[ChatResult]:
    try:
        result = await chat_with_llm(payload.messages)
    except LLMUpstreamError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "LLM_UPSTREAM_ERROR",
                "message": "LLM upstream request failed",
            },
        ) from exc
    return ok(result)


async def _stream_as_ndjson(
    messages: list[ChatMessage], *, request_id: str
) -> AsyncIterator[str]:
    outcome = "incomplete"
    try:
        async with aclosing(stream_chat_with_llm(messages)) as stream:
            async for event in stream:
                yield event.model_dump_json() + "\n"
                if isinstance(event, DoneEvent):
                    outcome = "completed"
                elif isinstance(event, ErrorEvent):
                    outcome = "upstream_error"
    except (asyncio.CancelledError, GeneratorExit):
        outcome = "cancelled"
        raise
    except LLMUpstreamError:
        outcome = "upstream_error"
        error = ErrorEvent(
            code="LLM_UPSTREAM_ERROR",
            message="LLM 上游流式请求失败",
            retryable=False,
        )
        yield error.model_dump_json() + "\n"
    finally:
        logger.info("chat stream closed request_id=%s outcome=%s", request_id, outcome)


@router.post("/chat/stream", dependencies=[Depends(verify_api_key)])
async def create_chat_stream(
    request: Request, payload: ChatRequest
) -> StreamingResponse:
    request_id = getattr(request.state, "request_id", "-")
    return StreamingResponse(
        _stream_as_ndjson(payload.messages, request_id=request_id),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
