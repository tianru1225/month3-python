from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.deps.auth import verify_api_key
from app.schemas.chat import ChatMessage, ChatRequest, ChatResult
from app.schemas.llm_stream import ErrorEvent
from app.schemas.response import ApiResponse
from app.services.errors import LLMUpstreamError
from app.services.llm_service import chat_with_llm, stream_chat_with_llm
from app.utils.response import ok

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


async def _stream_as_ndjson(messages: list[ChatMessage]) -> AsyncIterator[str]:
    try:
        async for event in stream_chat_with_llm(messages):
            yield event.model_dump_json() + "\n"
    except LLMUpstreamError:
        error = ErrorEvent(
            code="LLM_UPSTREAM_ERROR",
            message="LLM 上游流式请求失败",
            retryable=False,
        )
        yield error.model_dump_json() + "\n"


@router.post("/chat/stream", dependencies=[Depends(verify_api_key)])
async def create_chat_stream(payload: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_as_ndjson(payload.messages),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
